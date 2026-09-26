import asyncio
import logging

from bot_detector.firehose.app.auth.auth import ANONYMOUS_USER, AuthUser
from bot_detector.firehose.app.consumer import QueueRepoProtocol
from bot_detector.firehose.app.group_stream import (
    DelayedGroupStream,
    GroupStream,
)
from bot_detector.firehose.app.metrics import FIREHOSE_CONSUMERS, stream_type

logger = logging.getLogger(__name__)

# stream class per topic; unknown topics get the plain stream
TOPIC_STREAMS: dict[str, type[GroupStream]] = {
    "players.scraped": GroupStream,
    "reports.to_insert": DelayedGroupStream,
}


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
            stream_cls = TOPIC_STREAMS.get(topic, GroupStream)
            stream = stream_cls(
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
