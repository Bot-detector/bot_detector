import asyncio
import logging
from typing import Any, Generic, Optional, Type, TypeVar

from bot_detector.event_queue.core.interface import (
    QueueBackendConsumerProtocol,
    QueueBackendProducerProtocol,
    QueueBackendProtocol,
)
from bot_detector.event_queue.core.metrics import MESSAGES_SKIPPED
from pydantic import BaseModel, ValidationError

from .config import InMemoryConfig

T = TypeVar("T", bound=BaseModel)


class _InMemoryBase(Generic[T]):
    def __init__(self, cls: Type[T], config: InMemoryConfig):
        self.cls = cls
        self._queue = asyncio.Queue(config.maxsize)
        self.logger = logging.getLogger(cls.__name__)

    async def start(self) -> None:
        self.logger.info("[Memory] Queue initialized")

    async def stop(self) -> None:
        self.logger.info("[Memory] Queue stopped (contents left in place)")

    async def _validate(self, item: Any) -> T | ValidationError:
        try:
            return self.cls.model_validate(item)
        except ValidationError as e:
            return e


class InMemoryConsumerAdapter(
    _InMemoryBase[T],
    QueueBackendConsumerProtocol[T],
):
    async def get_one(self) -> Optional[T] | Exception:
        try:
            item = self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return None
        return await self._validate(item)

    async def get_many(self, count: int) -> list[T]:
        results = []
        for _ in range(count):
            try:
                item = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            validated = await self._validate(item)
            if isinstance(validated, Exception):
                MESSAGES_SKIPPED.inc()
                self.logger.warning(f"skipping invalid message: {validated}")
                continue
            results.append(validated)
        return results

    async def commit(self) -> Optional[Exception]:
        # no offsets to commit in memory; task_done() bookkeeping would
        # raise ValueError whenever commits outnumber dequeues
        return None


class InMemoryProducerAdapter(
    _InMemoryBase[T],
    QueueBackendProducerProtocol[T],
):
    async def put(self, messages: list[T]) -> None:
        # a full queue blocks the producer: bounded-queue backpressure,
        # on purpose (the paired consumer drains it)
        for message in messages:
            await self._queue.put(message)


class InMemoryAdapter(QueueBackendProtocol[T]):
    def __init__(
        self,
        cls: Type[T],
        config: InMemoryConfig | None = None,
    ):
        config = config or InMemoryConfig()
        shared_queue = asyncio.Queue(config.maxsize)
        self.producer = InMemoryProducerAdapter(cls, config)
        self.consumer = InMemoryConsumerAdapter(cls, config)

        # Make both use the same underlying queue
        self.producer._queue = shared_queue
        self.consumer._queue = shared_queue

    async def start(self) -> None:
        await self.producer.start()
        await self.consumer.start()

    async def stop(self) -> None:
        await self.producer.stop()
        await self.consumer.stop()

    async def put(self, messages: list[T]) -> None:
        await self.producer.put(messages)

    async def get_one(self) -> Optional[T] | Exception:
        return await self.consumer.get_one()

    async def get_many(self, count: int) -> list[T]:
        return await self.consumer.get_many(count)

    async def commit(self) -> Optional[Exception]:
        return await self.consumer.commit()
