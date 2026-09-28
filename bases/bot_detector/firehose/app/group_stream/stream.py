import asyncio
import logging

from bot_detector.event_queue.core import QueueConsumer
from bot_detector.firehose.app.group_stream.structs import QUEUE_MAX_SIZE
from bot_detector.firehose.app.metrics import FIREHOSE_DROPPED, stream_type
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class GroupStream:
    """One shared kafka consumer fanned out to connections.

    Anonymous streams fan out: every subscriber (one per websocket
    connection) gets a copy of each message through its own queue; a
    full inbox always appends, evicting its oldest message, so one slow
    client never stalls the others and re-syncs to the newest tail.

    Keyed streams compete: connections share one queue and each message
    is delivered exactly once, to whichever connection asks first (the
    api layer broadcasts it to the group's connections).
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
        self._fanout = anonymous
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_MAX_SIZE)
        self._subscribers: list[asyncio.Queue] = []
        self._loop = loop
        self._task = loop.create_task(self._pump())

    def subscribe(self) -> asyncio.Queue | None:
        """Register a per-connection inbox; None for compete streams."""
        if not self._fanout:
            return None
        inbox: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_MAX_SIZE)
        self._subscribers.append(inbox)
        return inbox

    def unsubscribe(self, inbox: asyncio.Queue | None) -> None:
        if inbox is not None and inbox in self._subscribers:
            self._subscribers.remove(inbox)

    async def get(self) -> BaseModel | Exception:
        return await self._queue.get()

    async def _hold(self, message: BaseModel | Exception | None) -> bool:
        """Gate between kafka and the queues; False drops the message."""
        return True

    async def _deliver(self, message: BaseModel | Exception | None) -> None:
        if not self._fanout:
            await self._queue.put(message)
            return
        for inbox in list(self._subscribers):
            try:
                inbox.put_nowait(message)
            except asyncio.QueueFull:
                # append always succeeds: evict the oldest message so a
                # slow connection re-syncs to the newest tail instead of
                # missing everything going forward
                _ = inbox.get_nowait()
                inbox.put_nowait(message)
                FIREHOSE_DROPPED.labels(topic=self.topic, type=self.type).inc()
                logger.warning(
                    f"slow connection, evicting oldest message group={self.group}"
                )

    async def _pump(self) -> None:
        try:
            await self._consumer.start()
            while True:
                message = await self._consumer.get_one()
                if not await self._hold(message=message):
                    continue
                await self._deliver(message)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception(f"pump failed for group={self.group}")

    async def stop(self) -> None:
        self._task.cancel()
        await self._consumer.stop()
