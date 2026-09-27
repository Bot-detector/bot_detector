import asyncio

import pytest
from bot_detector.event_queue.core import QueueConsumer
from bot_detector.event_queue.structs import ScrapedStruct
from bot_detector.firehose.app.auth.auth import AuthUser
from bot_detector.firehose.app.consumer_manager import ConsumerManager, GroupStream
from bot_detector.firehose.app.group_stream import (
    DELAYED_TOPIC,
    DelayedGroupStream,
)
from prometheus_client import REGISTRY

TOPIC = "players.scraped"


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
        if not self.messages:
            await asyncio.sleep(0.01)
            return None
        return self.messages.pop(0)


class FakeQueueRepo:
    def __init__(self):
        self.consumers: dict[str, FakeConsumer] = {}

    def resolve_consumer_group(self, user: AuthUser, topic: str) -> str:
        if user.name == "anonymous":
            return f"firehose-anonymous-{topic}"
        return f"firehose-{user.name}"

    def create_consumer(
        self, user: AuthUser, topic: str
    ) -> QueueConsumer[ScrapedStruct] | Exception:
        group = self.resolve_consumer_group(user=user, topic=topic)
        if group not in self.consumers:
            self.consumers[group] = FakeConsumer(group=group)
        return self.consumers[group]


def make_manager() -> tuple[ConsumerManager, FakeQueueRepo]:
    repo = FakeQueueRepo()
    return ConsumerManager(queue_repo=repo), repo


def gauge_value(topic: str, type_: str) -> float | None:
    return REGISTRY.get_sample_value(
        "firehose_consumers", {"topic": topic, "type": type_}
    )


@pytest.mark.asyncio
async def test_get_returns_same_stream_for_same_group():
    manager, _ = make_manager()
    user_a = AuthUser(name="system-one")
    user_b = AuthUser(name="system-one")
    topic = "players.scraped"

    stream_a = manager.get(user=user_a, topic=topic)
    stream_b = manager.get(user=user_b, topic=topic)

    assert isinstance(stream_a, GroupStream)
    assert stream_a is stream_b
    assert stream_a.count == 2


@pytest.mark.asyncio
async def test_get_returns_different_streams_per_topic():
    manager, _ = make_manager()
    user = AuthUser(name="system-one")

    stream_a = manager.get(user=user, topic="players.scraped")
    stream_b = manager.get(user=user, topic="reports.to_insert")

    assert isinstance(stream_a, GroupStream)
    assert isinstance(stream_b, GroupStream)
    assert stream_a is not stream_b
    assert stream_a.topic != stream_b.topic


@pytest.mark.asyncio
async def test_release_stops_consumer_when_last_client_leaves():
    manager, repo = make_manager()
    user = AuthUser(name="system-one")
    topic = "players.scraped"
    stream = manager.get(user=user, topic=topic)
    assert isinstance(stream, GroupStream)
    consumer = repo.consumers[stream.group]

    await manager.release(user=user, topic=topic)

    assert consumer.stopped is True
    assert (topic, stream.group) not in manager._streams


@pytest.mark.asyncio
async def test_release_keeps_consumer_while_clients_connected():
    manager, repo = make_manager()
    user_a = AuthUser(name="system-one")
    user_b = AuthUser(name="system-one")
    topic = "players.scraped"
    stream = manager.get(user=user_a, topic=topic)
    assert isinstance(stream, GroupStream)
    manager.get(user=user_b, topic=topic)
    consumer = repo.consumers[stream.group]

    await manager.release(user=user_a, topic=topic)

    assert consumer.stopped is False

    await manager.release(user=user_b, topic=topic)

    assert consumer.stopped is True


@pytest.mark.asyncio
async def test_pump_delivers_messages_and_errors_as_values():
    manager, repo = make_manager()
    user = AuthUser(name="system-one")
    topic = "players.scraped"
    stream = manager.get(user=user, topic=topic)
    assert isinstance(stream, GroupStream)
    consumer = repo.consumers[stream.group]

    message = ScrapedStruct.model_construct()
    error = RuntimeError("kafka down")
    consumer.messages.extend([message, error])

    first = await asyncio.wait_for(stream.get(), timeout=2)
    second = await asyncio.wait_for(stream.get(), timeout=2)

    assert first is message
    assert second is error

    await manager.release(user=user, topic=topic)


@pytest.mark.asyncio
async def test_consumer_gauges_track_lifecycle():
    topic = "players.scraped"
    manager, _ = make_manager()
    user = AuthUser(name="system-one")

    before = gauge_value(topic, "keyed") or 0
    stream = manager.get(user=user, topic=topic)
    assert isinstance(stream, GroupStream)
    after_get = gauge_value(topic, "keyed")

    assert after_get == before + 1

    await manager.release(user=user, topic=topic)
    assert gauge_value(topic, "keyed") == before


@pytest.mark.asyncio
async def test_reports_topic_gets_delayed_stream():
    manager, _ = make_manager()
    user = AuthUser(name="system-one")

    stream = manager.get(user=user, topic=DELAYED_TOPIC)

    assert isinstance(stream, DelayedGroupStream)
    assert stream.DELAY_S == 2 * 60 * 60

    await manager.release(user=user, topic=DELAYED_TOPIC)
