import asyncio
import json
from types import SimpleNamespace

import pytest
from bot_detector.event_queue.core import QueueConsumer
from bot_detector.event_queue.structs import ReportsToInsertStruct, ScrapedStruct
from bot_detector.firehose.api.dependencies import auth_user
from bot_detector.firehose.api.firehose import firehose
from bot_detector.firehose.app.auth.auth import ANONYMOUS, AuthUser, InvalidApiKey
from bot_detector.firehose.app.connection_manager import ConnectionManager
from bot_detector.firehose.app.exchange import Exchange
from bot_detector.firehose.app.queue_manager import QueueManager
from bot_detector.firehose.core.config import Settings
from fastapi import WebSocketException

TOPIC = "players.scraped"
REPORTS_TOPIC = "reports.to_insert"
N = 3
KEYED = AuthUser(name="system-one", scopes=["firehose.reports.to_insert"])


class FakeConsumer(QueueConsumer[ScrapedStruct]):
    def __init__(self, group: str):
        self.group = group
        self.started = False
        self.stopped = False
        self.messages: list[ScrapedStruct | Exception] = []

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def get_one(self):
        # like the real kafka consumer: block until a message exists
        while not self.messages:
            await asyncio.sleep(0.01)
        return self.messages.pop(0)


class FakeQueueRepo:
    def __init__(self):
        self.consumers: dict[str, FakeConsumer] = {}

    def resolve_consumer_group(self, user: AuthUser, topic: str) -> str:
        return f"fh-anonymous-{topic}"

    def create_consumer(
        self, user: AuthUser, topic: str
    ) -> QueueConsumer[ScrapedStruct] | Exception:
        group = self.resolve_consumer_group(user=user, topic=topic)
        if group not in self.consumers:
            self.consumers[group] = FakeConsumer(group=group)
        return self.consumers[group]


class FakeAuthRepo:
    async def authenticate(self, api_key: str | None, topic: str) -> AuthUser:
        return ANONYMOUS


class FakeKeyedAuthRepo:
    """Stands in for a valid api key: every topic authenticates keyed."""

    async def authenticate(self, api_key: str | None, topic: str) -> AuthUser:
        return AuthUser(name="system-one", scopes=[f"firehose.{topic}"])


class FakeDenyAuthRepo:
    async def authenticate(self, api_key: str | None, topic: str) -> Exception:
        return InvalidApiKey("not allowlisted")


class FakeWebSocket:
    def __init__(self, state):
        self.sent: list[str] = []
        self.state = SimpleNamespace()
        self.app = SimpleNamespace(state=SimpleNamespace(firehose=state))
        self.query_params = {"anonymous": "1"}
        self.headers: dict[str, str] = {}
        self.client = None
        self.accepted = False
        self.closed: tuple | None = None
        self._incoming: asyncio.Queue = asyncio.Queue()

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, data: str) -> None:
        self.sent.append(data)

    async def close(self, code: int | None = None, reason: str | None = None) -> None:
        self.closed = (code, reason)

    def client_disconnect(self, code: int = 1001) -> None:
        """Simulate the ASGI server delivering a client disconnect."""
        self._incoming.put_nowait({"type": "websocket.disconnect", "code": code})

    async def receive(self) -> dict:
        # like the ASGI websocket: blocks until a client event
        return await self._incoming.get()


def make_state(
    auth_repo: FakeAuthRepo | FakeKeyedAuthRepo | FakeDenyAuthRepo | None = None,
) -> tuple[SimpleNamespace, FakeConsumer]:
    repo = FakeQueueRepo()
    consumer = FakeConsumer(group=f"fh-anonymous-{TOPIC}")
    repo.consumers[consumer.group] = consumer  # create_consumer reuses this
    exchange = Exchange()
    state = SimpleNamespace(
        settings=Settings(),
        queue_repo=repo,
        exchange=exchange,
        queue_manager=QueueManager(queue_repo=repo, exchange=exchange),
        auth_repo=auth_repo or FakeAuthRepo(),
        connection_manager=ConnectionManager(),
        keyed_only_topics={"reports.to_insert"},
        http_session=None,
        discord_oauth=None,
    )
    return state, consumer


async def wait_for(condition, timeout: float = 5) -> None:
    async def run() -> None:
        while not condition():
            await asyncio.sleep(0.01)

    await asyncio.wait_for(run(), timeout=timeout)


@pytest.mark.asyncio
async def test_anonymous_connection_receives_fan_out_messages():
    state, consumer = make_state()
    ws = FakeWebSocket(state=state)

    # direct calls skip the auth dependency: simulate the accepted,
    # authenticated state it leaves behind
    await ws.accept()
    task = asyncio.create_task(firehose(websocket=ws, topic=TOPIC, user=ANONYMOUS))
    try:
        consumer.messages = _messages()

        await wait_for(lambda: len(ws.sent) >= N)

        got = [json.loads(m)["player_data"]["id"] for m in ws.sent]
        assert got == list(range(N))
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    assert ws.closed is None  # server never closed; we cancelled


@pytest.mark.asyncio
async def test_unknown_topic_closes_with_4404():
    state, _ = make_state()
    ws = FakeWebSocket(state=state)

    await firehose(websocket=ws, topic="not.a.topic", user=ANONYMOUS)

    assert ws.closed == (4404, "unknown topic")


@pytest.mark.asyncio
async def test_keyed_connection_streams_keyed_only_topic():
    state, _ = make_state()
    # handle for message injection: the route creates this consumer
    consumer = FakeConsumer(group=f"fh-anonymous-{REPORTS_TOPIC}")
    state.queue_repo.consumers[consumer.group] = consumer
    ws = FakeWebSocket(state=state)
    await ws.accept()

    task = asyncio.create_task(firehose(websocket=ws, topic=REPORTS_TOPIC, user=KEYED))
    try:
        # reports streams 2h behind live: the pump drops messages the
        # DelayAdapter cannot timestamp, so inject ts-shaped reports
        consumer.messages = [
            ReportsToInsertStruct.model_validate(
                {
                    "metadata": {"version": 1, "source": "test"},
                    "report": {
                        "reporter_id": 0,
                        "reported_id": 1,
                        "ts": 1,
                        "equipment": {},
                    },
                }
            )
        ]

        await wait_for(lambda: len(ws.sent) >= 1)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    assert ws.closed is None


@pytest.mark.asyncio
async def test_stale_handshake_event_does_not_stall_delivery():
    """uvicorn can deliver the ASGI 'websocket.connect' event to the
    route's long-lived receive task; the route must recover (park a
    fresh receive) and keep draining instead of spinning and
    discarding inbox messages."""
    state, consumer = make_state()
    ws = FakeWebSocket(state=state)
    # the ASGI handshake event arrives before anything else
    ws._incoming.put_nowait({"type": "websocket.connect"})
    await ws.accept()

    task = asyncio.create_task(firehose(websocket=ws, topic=TOPIC, user=ANONYMOUS))
    try:
        consumer.messages = _messages()

        await wait_for(lambda: len(ws.sent) >= N)

        got = [json.loads(m)["player_data"]["id"] for m in ws.sent]
        assert got == list(range(N))
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_idle_disconnect_releases_stream_and_consumer():
    state, consumer = make_state()
    ws = FakeWebSocket(state=state)

    task = asyncio.create_task(firehose(websocket=ws, topic=TOPIC, user=ANONYMOUS))
    await ws.accept()
    try:
        # client vanishes while no messages flow: the handler must wake
        # on the disconnect (not stay parked on the empty inbox), clean
        # up, and release the shared stream
        ws.client_disconnect()
        await asyncio.wait_for(task, timeout=2)

        assert consumer.stopped is True
        assert state.connection_manager.count(group=consumer.group) == 0
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


def _messages() -> list[ScrapedStruct]:
    return [
        ScrapedStruct.model_construct(
            metadata={"version": 1, "source": "test"},
            player_data={"id": i, "name": f"player_{i}"},
            highscore_data=None,
        )
        for i in range(N)
    ]


@pytest.mark.asyncio
async def test_auth_dependency_accepts_and_returns_anonymous():
    state, _ = make_state()
    ws = FakeWebSocket(state=state)

    user = await auth_user(websocket=ws, topic=TOPIC)

    assert ws.accepted is True  # accept first, so closes arrive as frames
    assert user == ANONYMOUS


@pytest.mark.asyncio
async def test_auth_dependency_closes_anonymous_on_keyed_topics():
    state, _ = make_state()
    ws = FakeWebSocket(state=state)

    with pytest.raises(WebSocketException) as raised:
        await auth_user(websocket=ws, topic=REPORTS_TOPIC)

    assert ws.accepted is True
    assert (raised.value.code, raised.value.reason) == (
        4403,
        "topic requires an api key",
    )


@pytest.mark.asyncio
async def test_auth_dependency_passes_keyed_users():
    state, _ = make_state(auth_repo=FakeKeyedAuthRepo())
    ws = FakeWebSocket(state=state)
    ws.query_params = {}  # no anonymous flag: the api-key path

    user = await auth_user(websocket=ws, topic=REPORTS_TOPIC)

    assert user == KEYED


@pytest.mark.asyncio
async def test_auth_dependency_closes_invalid_credentials():
    state, _ = make_state(auth_repo=FakeDenyAuthRepo())
    ws = FakeWebSocket(state=state)
    ws.query_params = {}

    with pytest.raises(WebSocketException) as raised:
        await auth_user(websocket=ws, topic=TOPIC)

    assert (raised.value.code, raised.value.reason) == (4401, "invalid api key")
