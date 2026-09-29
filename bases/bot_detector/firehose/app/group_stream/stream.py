import asyncio
import logging
import uuid

from bot_detector.event_queue.core import QueueConsumer
from bot_detector.firehose.app.group_stream.structs import QUEUE_MAX_SIZE, Inbox
from bot_detector.firehose.app.metrics import FIREHOSE_DROPPED, stream_type
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# how often the pump re-checks for inbox space while every inbox is full
POLL_INTERVAL_S = 0.01

# short id length for unnamed subscribers (log identification only)
SHORT_ID_CHARS = 8


class GroupStream:
    """One shared kafka consumer fanned out to connections.

    Every subscriber (one per websocket connection, anonymous or keyed)
    gets a copy of each message through its own inbox.

    - while at least one inbox has space, a full inbox always appends,
      evicting its oldest message, so a slow connection re-syncs to the
      newest tail without stalling the others
    - while every inbox is full nobody is consuming; the pump waits
      instead of destroying messages (kafka retains the stream until a
      connection catches up)
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
        self._subscribers: list[Inbox] = []
        self._loop = loop
        self._task = loop.create_task(self._pump())

    def subscribe(self, name: str | None = None) -> Inbox:
        """Register a per-connection inbox.

        Unnamed subscribers get a short uuid, enough to tell eviction
        log lines apart.
        """
        inbox = Inbox(
            name=name or uuid.uuid4().hex[-SHORT_ID_CHARS:],
            queue=asyncio.Queue(maxsize=QUEUE_MAX_SIZE),
        )
        self._subscribers.append(inbox)
        return inbox

    def unsubscribe(self, inbox: Inbox) -> None:
        if inbox in self._subscribers:
            self._subscribers.remove(inbox)

    async def _hold(self, message: BaseModel | Exception | None) -> bool:
        """Gate between kafka and the queues; False drops the message."""
        return True

    async def _deliver(self, message: BaseModel | Exception | None) -> None:
        # every inbox full = nobody consuming; wait rather than destroy
        # messages (kafka retains the stream until a connection catches up)
        while self._subscribers and all(
            inbox.queue.full() for inbox in self._subscribers
        ):
            await asyncio.sleep(POLL_INTERVAL_S)
        for inbox in list(self._subscribers):
            try:
                inbox.queue.put_nowait(message)
            except asyncio.QueueFull:
                # append always succeeds: evict the oldest message so a
                # slow connection re-syncs to the newest tail; another
                # connection still has capacity, so the stream is live
                _ = inbox.queue.get_nowait()
                inbox.queue.put_nowait(message)
                FIREHOSE_DROPPED.labels(topic=self.topic, type=self.type).inc()
                logger.warning(
                    "inbox full, evicting oldest "
                    f"subscriber={inbox.name} group={self.group}"
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
