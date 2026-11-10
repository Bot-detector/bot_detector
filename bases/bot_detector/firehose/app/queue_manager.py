import asyncio
import logging
from dataclasses import dataclass

from bot_detector.event_queue.core import QueueConsumer
from bot_detector.firehose.app.auth.auth import ANONYMOUS_USER, AuthUser
from bot_detector.firehose.app.consumer import QueueRepoProtocol
from bot_detector.firehose.app.exchange import DelayAdapter, Exchange
from bot_detector.firehose.app.exchange.structs import serialize
from bot_detector.firehose.app.metrics import FIREHOSE_CONSUMERS, QueueType, stream_type
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# emission delay per topic; unknown topics stream live
TOPIC_HOLDS: dict[str, DelayAdapter] = {
    "reports.to_insert": DelayAdapter(delay_s=2 * 60 * 60),
}

# pause after a consumer error / poison payload so a tight fault loop
# cannot spin the pump; applied once per fault, at the pump, never per
# websocket route
ERROR_BACKOFF_S = 0.5


@dataclass
class Queue:
    """One kafka consumer plus its pump, per (topic, consumer group)."""

    topic: str
    group: str
    type: QueueType
    consumer: QueueConsumer[BaseModel]
    task: asyncio.Task[None] | None = None


class QueueManager:
    """Owns the kafka queues: one consumer per (topic, consumer group).

    - create(): build the consumer, register and start the pump
    - delete(): stop the pump and consumer, unregister ("kill the queue")
    - get()/release(): refcounted wrappers so many connections share one
      queue; create happens on first acquire, delete on last release

    The pump pushes a copy into every inbox the Exchange holds for the
    group and stops when the group has no subscribers left; kafka
    retains the backlog for the next connection.
    """

    def __init__(self, queue_repo: QueueRepoProtocol, exchange: Exchange):
        self._queue_repo = queue_repo
        self._exchange = exchange
        self._queues: dict[tuple[str, str], Queue] = {}

    def create(self, user: AuthUser, topic: str) -> Queue | Exception:
        """Build, register and start the queue for (topic, group).

        Sync on purpose: the asyncio loop makes it atomic, so two
        connections racing on the same group cannot create twice.
        """
        loop = asyncio.get_running_loop()
        group = self._queue_repo.resolve_consumer_group(user=user, topic=topic)
        existing = self._queues.get((topic, group))
        if existing is not None:
            # the pump can have stopped itself while the last
            # connections were draining; revive it for the new subscriber
            if existing.task is None or existing.task.done():
                existing.task = loop.create_task(self._consume(existing))
            return existing
        consumer = self._queue_repo.create_consumer(user=user, topic=topic)
        if isinstance(consumer, Exception):
            return consumer
        anonymous = user.name == ANONYMOUS_USER
        queue = Queue(
            topic=topic,
            group=group,
            type=stream_type(anonymous=anonymous),
            consumer=consumer,
        )
        self._queues[(topic, group)] = queue
        queue.task = loop.create_task(self._consume(queue))
        FIREHOSE_CONSUMERS.labels(topic=topic, type=queue.type).inc()
        logger.info(f"queue created topic={topic} group={group}")
        return queue

    async def delete(self, user: AuthUser, topic: str) -> None:
        """Stop the queue for (topic, group) and unregister it."""
        group = self._queue_repo.resolve_consumer_group(user=user, topic=topic)
        queue = self._queues.pop((topic, group), None)
        if queue is None:
            return
        FIREHOSE_CONSUMERS.labels(topic=topic, type=queue.type).dec()
        logger.info(f"queue deleted topic={topic} group={group}")
        await self._stop(queue)

    def get(self, user: AuthUser, topic: str) -> Queue | Exception:
        """Acquire the queue for a connection, creating it on first use."""
        return self.create(user=user, topic=topic)

    async def release(self, user: AuthUser, topic: str) -> None:
        """Drop the connection's reference; delete when nobody subscribes.

        The exchange registry is the single source of truth for liveness:
        an empty subscriber list means the queue is killed and kafka
        retains the backlog.
        """
        group = self._queue_repo.resolve_consumer_group(user=user, topic=topic)
        if self._queues.get((topic, group)) is None:
            return
        if self._exchange.get_subscribers(topic=topic, group=group):
            return
        await self.delete(user=user, topic=topic)

    async def shutdown(self) -> None:
        for key, queue in list(self._queues.items()):
            logger.info(f"stopping queue topic={queue.topic} group={queue.group}")
            self._queues.pop(key, None)
            await self._stop(queue)

    async def _stop(self, queue: Queue) -> None:
        # the manager alone closes the consumer: the pump may be
        # cancelled before its first tick, so its own cleanup cannot be
        # relied on
        if queue.task is not None:
            queue.task.cancel()
            await asyncio.gather(queue.task, return_exceptions=True)
            queue.task = None
        await queue.consumer.stop()

    async def _consume(self, queue: Queue) -> None:
        """Pump kafka into the exchange; an empty subscriber list stops it."""
        hold = TOPIC_HOLDS.get(queue.topic)
        try:
            await queue.consumer.start()
            while True:
                subscribers = self._exchange.get_subscribers(
                    topic=queue.topic, group=queue.group
                )
                if not subscribers:
                    # nobody is listening: stop consuming, kafka retains
                    # the backlog for the next connection
                    break
                message = await queue.consumer.get_one()
                if message is None:
                    continue
                if hold is not None and not await hold.hold(message=message):
                    continue
                # serialize once per message here (the consume loop),
                # not once per connection: every inbox receives the
                # same ready payload. consumer errors and poison
                # payloads never reach the websockets: they are a pump
                # concern - log, pause once, move on (kafka retains)
                if not isinstance(message, BaseModel):
                    logger.warning(f"skipping message: {message}")
                    await asyncio.sleep(ERROR_BACKOFF_S)
                    continue
                payload = serialize(message)
                # a copy for every subscriber; backpressure inside the
                # exchange (full inbox = kick, last subscriber = wait)
                # is not the pump's problem. exactly one yield per kafka
                # message afterwards: routes need turns to drain, but
                # every sleep(0) costs a full event-loop cycle (~1ms
                # under uvicorn), so yielding per send would cap the
                # pump at ~50 msg/s per group
                for conn_id in subscribers:
                    await self._exchange.send_or_wait(
                        conn_id=conn_id,
                        topic=queue.topic,
                        group=queue.group,
                        message=payload,
                    )
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception(f"consume failed topic={queue.topic} group={queue.group}")
