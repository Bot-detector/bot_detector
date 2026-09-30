import asyncio
import json
from types import SimpleNamespace

import pytest
from bot_detector.event_queue.core import QueueConsumer
from bot_detector.event_queue.structs import ScrapedStruct
from bot_detector.firehose.api.firehose import firehose
from bot_detector.firehose.app.auth.auth import ANONYMOUS, AuthUser
from bot_detector.firehose.app.connection_manager import ConnectionManager
from bot_detector.firehose.app.exchange import Exchange
from bot_detector.firehose.app.queue_manager import QueueManager
from bot_detector.firehose.core.config import Settings

TOPIC = "players.scraped"
N = 3


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


def make_state() -> tuple[SimpleNamespace, FakeConsumer]:
    repo = FakeQueueRepo()
    consumer = FakeConsumer(group=f"fh-anonymous-{TOPIC}")
    repo.consumers[consumer.group] = consumer  # create_consumer reuses this
    exchange = Exchange()
    state = SimpleNamespace(
        settings=Settings(),
        queue_repo=repo,
        exchange=exchange,
        queue_manager=QueueManager(queue_repo=repo, exchange=exchange),
        auth_repo=FakeAuthRepo(),
        connection_manager=ConnectionManager(),
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

    task = asyncio.create_task(firehose(websocket=ws, topic=TOPIC))
    try:
        assert await asyncio.wait_for(asyncio.shield(_accepted(ws)), timeout=5)
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

    await firehose(websocket=ws, topic="not.a.topic")

    assert ws.closed == (4404, "unknown topic")
    assert ws.accepted is False


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

    task = asyncio.create_task(firehose(websocket=ws, topic=TOPIC))
    try:
        await wait_for(lambda: ws.accepted)
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

    task = asyncio.create_task(firehose(websocket=ws, topic=TOPIC))
    try:
        await wait_for(lambda: ws.accepted)

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


async def _accepted(ws: FakeWebSocket) -> bool:
    while not ws.accepted:
        await asyncio.sleep(0.01)
    return True
