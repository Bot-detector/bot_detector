import asyncio

import pytest
from bot_detector.event_queue.core import QueueConsumer
from bot_detector.event_queue.structs import ScrapedStruct
from bot_detector.firehose.app.auth.auth import AuthUser
from bot_detector.firehose.app.exchange import Exchange
from bot_detector.firehose.app.exchange.structs import serialize
from bot_detector.firehose.app.queue_manager import Queue, QueueManager, TOPIC_HOLDS
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


def make_manager() -> tuple[QueueManager, FakeQueueRepo, Exchange]:
    repo = FakeQueueRepo()
    exchange = Exchange()
    return QueueManager(queue_repo=repo, exchange=exchange), repo, exchange


def gauge_value(topic: str, type_: str) -> float | None:
    return REGISTRY.get_sample_value(
        "firehose_consumers", {"topic": topic, "type": type_}
    )


@pytest.mark.asyncio
async def test_create_builds_registers_and_starts():
    manager, repo, _ = make_manager()
    user = AuthUser(name="system-one")

    queue = manager.create(user=user, topic=TOPIC)

    assert isinstance(queue, Queue)
    assert (TOPIC, queue.group) in manager._queues
    consumer = repo.consumers[queue.group]
    # the pump opens the consumer on its first loop tick
    await asyncio.sleep(0)
    assert consumer.started is True

    # create is idempotent per (topic, group): the same queue returns
    again = manager.create(user=user, topic=TOPIC)
    assert again is queue

    await manager.delete(user=user, topic=TOPIC)


@pytest.mark.asyncio
async def test_delete_stops_and_unregisters():
    manager, repo, _ = make_manager()
    user = AuthUser(name="system-one")

    queue = manager.create(user=user, topic=TOPIC)
    consumer = repo.consumers[queue.group]

    await manager.delete(user=user, topic=TOPIC)

    assert consumer.stopped is True
    assert manager._queues == {}

    # delete is a no-op when nothing is registered
    await manager.delete(user=user, topic=TOPIC)


@pytest.mark.asyncio
async def test_release_keeps_queue_while_subscribers_remain():
    manager, repo, exchange = make_manager()
    user = AuthUser(name="system-one")

    queue = manager.get(user=user, topic=TOPIC)
    assert isinstance(queue, Queue)
    exchange.subscribe(topic=TOPIC, group=queue.group, conn_id="t1", user=user)
    consumer = repo.consumers[queue.group]

    # a subscriber exists: release must not kill the queue
    await manager.release(user=user, topic=TOPIC)
    assert (TOPIC, queue.group) in manager._queues
    assert consumer.stopped is False

    # last subscriber gone: the queue is killed, kafka retains the rest
    exchange.unsubscribe("t1")
    await manager.release(user=user, topic=TOPIC)
    assert manager._queues == {}
    assert consumer.stopped is True


@pytest.mark.asyncio
async def test_consume_delivers_to_exchange_inboxes():
    manager, repo, exchange = make_manager()
    user = AuthUser(name="system-one")

    queue = manager.get(user=user, topic=TOPIC)
    assert isinstance(queue, Queue)
    inbox = exchange.subscribe(topic=TOPIC, group=queue.group, conn_id="t1", user=user)
    consumer = repo.consumers[queue.group]

    message = ScrapedStruct.model_construct()
    error = RuntimeError("kafka down")
    consumer.messages.extend([message, error])

    first = await asyncio.wait_for(inbox.queue.get(), timeout=2)
    second = await asyncio.wait_for(inbox.queue.get(), timeout=2)

    # the pump serializes models once; errors pass through as values
    assert first == serialize(message)
    assert second is error

    await manager.release(user=user, topic=TOPIC)


@pytest.mark.asyncio
async def test_pump_stops_when_subscriber_list_empties():
    manager, repo, exchange = make_manager()
    user = AuthUser(name="system-one")

    queue = manager.get(user=user, topic=TOPIC)
    assert isinstance(queue, Queue)
    exchange.subscribe(topic=TOPIC, group=queue.group, conn_id="t1", user=user)
    consumer = repo.consumers[queue.group]

    # the group loses its last subscriber and its last reference; the
    # pump must stop itself
    exchange.unsubscribe("t1")
    await manager.release(user=user, topic=TOPIC)
    assert queue.task is None or queue.task.done()
    assert consumer.stopped is True


@pytest.mark.asyncio
async def test_consumer_gauges_track_lifecycle():
    manager, _, _ = make_manager()
    user = AuthUser(name="system-one")

    before = gauge_value(TOPIC, "keyed") or 0
    queue = manager.get(user=user, topic=TOPIC)
    assert isinstance(queue, Queue)
    after_get = gauge_value(TOPIC, "keyed")

    assert after_get == before + 1

    await manager.release(user=user, topic=TOPIC)
    assert gauge_value(TOPIC, "keyed") == before


def test_reports_topic_gets_the_delay_hold():
    hold = TOPIC_HOLDS["reports.to_insert"]
    assert hold.delay_s == 2 * 60 * 60


@pytest.mark.asyncio
async def test_anonymous_topic_gets_its_own_shared_group():
    manager, _, _ = make_manager()
    user = AuthUser(name="anonymous")

    queue = manager.get(user=user, topic=TOPIC)

    assert isinstance(queue, Queue)
    assert queue.group == f"firehose-anonymous-{TOPIC}"
    assert queue.type == "anonymous"

    await manager.release(user=user, topic=TOPIC)
