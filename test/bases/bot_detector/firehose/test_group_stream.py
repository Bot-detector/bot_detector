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

    message = ScrapedStruct.model_construct()
    error = RuntimeError("kafka down")
    consumer.messages.extend([message, error])

    assert await asyncio.wait_for(inbox_a.get(), timeout=2) is message
    assert await asyncio.wait_for(inbox_b.get(), timeout=2) is message
    assert await asyncio.wait_for(inbox_a.get(), timeout=2) is error
    assert await asyncio.wait_for(inbox_b.get(), timeout=2) is error

    await stream.stop()


@pytest.mark.asyncio
async def test_keyed_stream_delivers_once_and_subscribes_none():
    stream, consumer = make_stream(anonymous=False)
    assert stream.subscribe() is None

    message = ScrapedStruct.model_construct()
    consumer.messages.append(message)

    first = await asyncio.wait_for(stream.get(), timeout=2)
    assert first is message

    # delivered exactly once: the queue is empty now, so the next get
    # parks until the timeout
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(stream.get(), timeout=0.2)

    await stream.stop()

    await stream.stop()


@pytest.mark.asyncio
async def test_full_inbox_evicts_oldest_for_slow_subscriber():
    stream, consumer = make_stream(anonymous=True)
    slow = stream.subscribe()
    assert slow is not None

    total = QUEUE_MAX_SIZE + 1
    messages = [ScrapedStruct.model_construct() for _ in range(total)]
    consumer.messages.extend(messages)

    async def wait_full() -> None:
        while slow.qsize() < QUEUE_MAX_SIZE:
            await asyncio.sleep(0.01)

    await asyncio.wait_for(wait_full(), timeout=5)

    # one over the cap: the oldest was evicted, the newest tail kept
    held = [slow.get_nowait() for _ in range(slow.qsize())]
    assert held == messages[1:]

    await stream.stop()


@pytest.mark.asyncio
async def test_unsubscribe_stops_delivery():
    stream, consumer = make_stream(anonymous=True)
    inbox = stream.subscribe()
    assert inbox is not None

    stream.unsubscribe(inbox)
    stream.unsubscribe(None)

    consumer.messages.append(ScrapedStruct.model_construct())
    await asyncio.sleep(0.05)

    assert inbox.qsize() == 0

    await stream.stop()
