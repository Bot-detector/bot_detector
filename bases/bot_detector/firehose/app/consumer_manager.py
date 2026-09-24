import asyncio
import logging

from bot_detector.event_queue.core import QueueConsumer
from bot_detector.firehose.app.auth.auth import ANONYMOUS_USER, AuthUser
from bot_detector.firehose.app.consumer import QueueRepoProtocol
from bot_detector.firehose.app.metrics import FIREHOSE_CONSUMERS, stream_type
from pydantic import BaseModel

logger = logging.getLogger(__name__)

QUEUE_MAX_SIZE = 1000


def serialize(message: BaseModel) -> str:
    import orjson

    return orjson.dumps(message.model_dump()).decode("utf-8")


class GroupStream:
    """One shared kafka consumer fanned out over an internal queue.

    Multiple websocket connections may await get(); each message is
    delivered exactly once, to whichever connection asks first.
    """

    def __init__(
        self,
        topic: str,
        group: str,
        anonymous: bool,
        consumer: QueueConsumer[BaseModel],
        loop: asyncio.AbstractEventLoop,
    ):
        self.topic = topic
        self.group = group
        self.anonymous = anonymous
        self.type = stream_type(anonymous=anonymous)
        self.count = 0
        self._consumer = consumer
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_MAX_SIZE)
        self._loop = loop
        self._task = loop.create_task(self._pump())

    async def get(self) -> BaseModel | Exception:
        return await self._queue.get()

    async def _pump(self) -> None:
        try:
            await self._consumer.start()
            while True:
                message = await self._consumer.get_one()
                await self._queue.put(message)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception(f"pump failed for group={self.group}")

    async def stop(self) -> None:
        self._task.cancel()
        await self._consumer.stop()


class ConsumerManager:
    """Shares one kafka consumer per topic+consumer group (refcounted)."""

    def __init__(self, queue_repo: QueueRepoProtocol):
        self._queue_repo = queue_repo
        self._streams: dict[tuple[str, str], GroupStream] = {}

    def get(self, user: AuthUser, topic: str) -> GroupStream | Exception:
        loop = asyncio.get_running_loop()
        group = self._queue_repo.resolve_consumer_group(user=user, topic=topic)
        stream = self._streams.get((topic, group))
        if stream is None:
            consumer = self._queue_repo.create_consumer(user=user, topic=topic)
            if isinstance(consumer, Exception):
                return consumer
            anonymous = user.name == ANONYMOUS_USER
            stream = GroupStream(
                topic=topic,
                group=group,
                anonymous=anonymous,
                consumer=consumer,
                loop=loop,
            )
            self._streams[(topic, group)] = stream
            FIREHOSE_CONSUMERS.labels(
                topic=topic, type=stream_type(anonymous=anonymous)
            ).inc()
        stream.count += 1
        logger.info(f"stream acquired group={group} (total={stream.count})")
        return stream

    async def release(self, user: AuthUser, topic: str) -> None:
        group = self._queue_repo.resolve_consumer_group(user=user, topic=topic)
        stream = self._streams.get((topic, group))
        if stream is None:
            return
        stream.count -= 1
        if stream.count > 0:
            return
        logger.info(f"last client left group={group}, stopping consumer")
        self._streams.pop((topic, group), None)
        FIREHOSE_CONSUMERS.labels(
            topic=topic, type=stream_type(anonymous=stream.anonymous)
        ).dec()
        await stream.stop()

    async def shutdown(self) -> None:
        for key, stream in list(self._streams.items()):
            logger.info(f"stopping consumer group={stream.group}")
            self._streams.pop(key, None)
            await stream.stop()
