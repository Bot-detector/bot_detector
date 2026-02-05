import asyncio
import logging
from typing import Generic, Optional, Type, TypeVar

from bot_detector.event_queue.core.interface import (
    QueueBackendConsumerProtocol,
    QueueBackendProducerProtocol,
    QueueBackendProtocol,
)
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
        self.logger.info("[Memory] Queue cleared/stopped")

    async def _validate(self, item) -> Optional[T]:
        try:
            return self.cls.model_validate(item)
        except ValidationError as e:
            self.logger.warning(f"Validation failed: {e}")
            return None


class InMemoryConsumerAdapter(
    _InMemoryBase[T],
    QueueBackendConsumerProtocol[T],
):
    async def get_one(self) -> Optional[T]:
        try:
            item = self._queue.get_nowait()
            return await self._validate(item)
        except asyncio.QueueEmpty:
            return None

    async def get_many(self, count: int) -> list[T]:
        results = []
        for _ in range(count):
            try:
                item = self._queue.get_nowait()
                validated = await self._validate(item)
                if validated is not None:
                    results.append(validated)
            except asyncio.QueueEmpty:
                break
        return results

    async def commit(self) -> Optional[Exception]:
        self._queue.task_done()

    async def lag(self) -> int:
        return self._queue.qsize()


class InMemoryProducerAdapter(
    _InMemoryBase[T],
    QueueBackendProducerProtocol[T],
):
    async def put(self, messages: list[T]) -> None:
        for message in messages:
            await self._queue.put(message)


class InMemoryAdapter(QueueBackendProtocol[T]):
    def __init__(
        self,
        cls: Type[T],
        config: InMemoryConfig = InMemoryConfig(),
    ):
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

    async def get_one(self) -> Optional[T]:
        return await self.consumer.get_one()

    async def get_many(self, count: int) -> list[T]:
        return await self.consumer.get_many(count)

    async def commit(self) -> Optional[Exception]:
        return await self.consumer.commit()

    async def lag(self) -> int:
        return await self.consumer.lag()
