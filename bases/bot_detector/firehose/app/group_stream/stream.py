import asyncio
import logging

from bot_detector.event_queue.core import QueueConsumer
from bot_detector.firehose.app.group_stream.structs import QUEUE_MAX_SIZE
from bot_detector.firehose.app.metrics import stream_type
from pydantic import BaseModel

logger = logging.getLogger(__name__)


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

    async def _hold(self, message: BaseModel | Exception | None) -> bool:
        """Gate between kafka and the queue; False drops the message."""
        return True

    async def _pump(self) -> None:
        try:
            await self._consumer.start()
            while True:
                message = await self._consumer.get_one()
                if not await self._hold(message=message):
                    continue
                await self._queue.put(message)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception(f"pump failed for group={self.group}")

    async def stop(self) -> None:
        self._task.cancel()
        await self._consumer.stop()
