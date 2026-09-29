import asyncio

import pytest
from bot_detector.event_queue.core import QueueConsumer
from bot_detector.event_queue.structs import ScrapedStruct
from bot_detector.firehose.app.group_stream import GroupStream
from bot_detector.firehose.app.group_stream.structs import QUEUE_MAX_SIZE

TOPIC = "players.scraped"
GROUP = "fh-anonymous-players.scraped"


class FakeConsumer(QueueConsumer[ScrapedStruct]):
    def __init__(self, group: str):
        self.group = group
        self.messages: list[ScrapedStruct | Exception] = []

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def get_one(self):
        # like the real kafka consumer: block until a message exists
        while not self.messages:
            await asyncio.sleep(0.01)
        return self.messages.pop(0)


def make_stream(anonymous: bool) -> tuple[GroupStream, FakeConsumer]:
    consumer = FakeConsumer(group=GROUP)
    loop = asyncio.get_running_loop()
    stream = GroupStream(
        topic=TOPIC,
        group=GROUP,
        anonymous=anonymous,
        consumer=consumer,
        loop=loop,
    )
    return stream, consumer


@pytest.mark.asyncio
async def test_anonymous_stream_fans_out_to_each_subscriber():
    stream, consumer = make_stream(anonymous=True)
    inbox_a = stream.subscribe()
    inbox_b = stream.subscribe()
    assert inbox_a is not None
    assert inbox_b is not None
    assert inbox_a.name and inbox_b.name
    assert inbox_a.name != inbox_b.name

    message = ScrapedStruct.model_construct()
    error = RuntimeError("kafka down")
    consumer.messages.extend([message, error])

    assert await asyncio.wait_for(inbox_a.queue.get(), timeout=2) is message
    assert await asyncio.wait_for(inbox_b.queue.get(), timeout=2) is message
    assert await asyncio.wait_for(inbox_a.queue.get(), timeout=2) is error
    assert await asyncio.wait_for(inbox_b.queue.get(), timeout=2) is error

    await stream.stop()


@pytest.mark.asyncio
async def test_keyed_stream_fans_out_like_anonymous():
    stream, consumer = make_stream(anonymous=False)

    inbox_a = stream.subscribe(name="tab-1")
    inbox_b = stream.subscribe(name="tab-2")
    assert inbox_a is not None
    assert inbox_b is not None

    message = ScrapedStruct.model_construct()
    consumer.messages.append(message)

    assert await asyncio.wait_for(inbox_a.queue.get(), timeout=2) is message
    assert await asyncio.wait_for(inbox_b.queue.get(), timeout=2) is message

    await stream.stop()


@pytest.mark.asyncio
async def test_full_inbox_evicts_oldest_while_stream_is_live():
    stream, consumer = make_stream(anonymous=True)
    slow = stream.subscribe(name="slow")
    fast = stream.subscribe(name="fast")
    assert slow is not None
    assert fast is not None

    total = QUEUE_MAX_SIZE + 1
    messages = [ScrapedStruct.model_construct() for _ in range(total)]
    received: list[ScrapedStruct | Exception] = []

    async def drain() -> None:
        while len(received) < total:
            received.append(await fast.queue.get())

    drainer = asyncio.create_task(drain())
    consumer.messages.extend(messages)

    await asyncio.wait_for(drainer, timeout=10)

    # fast kept up and saw every message in order; the slow inbox
    # capped at max size and kept the newest tail (oldest evicted)
    assert received == messages
    held = [slow.queue.get_nowait() for _ in range(slow.queue.qsize())]
    assert held == messages[1:]

    await stream.stop()


@pytest.mark.asyncio
async def test_all_inboxes_full_waits_instead_of_evicting():
    stream, consumer = make_stream(anonymous=True)
    only = stream.subscribe(name="only")
    assert only is not None

    total = QUEUE_MAX_SIZE + 50
    messages = [ScrapedStruct.model_construct() for _ in range(total)]
    consumer.messages.extend(messages)

    got: list[ScrapedStruct | Exception] = []

    async def drain() -> None:
        while len(got) < total:
            got.append(await only.queue.get())

    drainer = asyncio.create_task(drain())
    await asyncio.wait_for(drainer, timeout=10)

    # sole subscriber: with every inbox full the pump waits, so the
    # client catches up with zero loss once it reads again
    assert got == messages
    assert only.queue.qsize() == 0

    await stream.stop()


@pytest.mark.asyncio
async def test_unsubscribe_stops_delivery():
    stream, consumer = make_stream(anonymous=True)
    inbox = stream.subscribe()
    assert inbox is not None

    stream.unsubscribe(inbox)

    consumer.messages.append(ScrapedStruct.model_construct())
    await asyncio.sleep(0.05)

    assert inbox.queue.qsize() == 0

    await stream.stop()
