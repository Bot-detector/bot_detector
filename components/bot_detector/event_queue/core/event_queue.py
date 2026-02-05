from typing import Generic, Optional, TypeVar

from pydantic import BaseModel

from .interface import (
    QueueBackendConsumerProtocol,
    QueueBackendProducerProtocol,
    QueueBackendProtocol,
)

T = TypeVar("T", bound=BaseModel)


class QueueProducer(Generic[T]):
    """
    High-level Queue class used by the application.
    It relies on Dependency Injection to get the specific backend.

    Example:
        config = InMemoryConfig(maxsize=50)
        adapter = InMemoryProducerAdapter(PlayerScraped, config=config)
        queue = QueueProducer[PlayerScraped](backend=adapter)
        await queue.put()
    """

    def __init__(self, backend: QueueBackendProducerProtocol):
        self._backend = backend

    async def start(self):
        await self._backend.start()

    async def stop(self):
        await self._backend.stop()

    async def put(self, message: list[T]):
        await self._backend.put(message)


class QueueConsumer(Generic[T]):
    """
    High-level Queue class used by the application.
    It relies on Dependency Injection to get the specific backend.

    Example:
        config = InMemoryConfig(maxsize=50)
        adapter = InMemoryConsumerAdapter(PlayerScraped, config=config)
        queue = QueueConsumer[PlayerScraped](backend=adapter)
        await queue.get_one()
        await queue.get_many()
    """

    def __init__(self, backend: QueueBackendConsumerProtocol):
        self._backend = backend

    async def start(self):
        await self._backend.start()

    async def stop(self):
        await self._backend.stop()

    async def get_one(self) -> Optional[T] | Exception:
        return await self._backend.get_one()

    async def get_many(self, count: int) -> list[T] | Exception:
        return await self._backend.get_many(count)


class Queue(QueueConsumer[T], QueueProducer[T]):
    """
    High-level Queue class used by the application.
    It relies on Dependency Injection to get the specific backend.

    Example:
        config = InMemoryConfig(maxsize=50)
        adapter = InMemoryAdapter(PlayerScraped, config=config)
        queue = Queue[PlayerScraped](backend=adapter)
        await queue.put()
        await queue.get_one()
        await queue.get_many()
    """

    def __init__(self, backend: QueueBackendProtocol):
        self._backend = backend
