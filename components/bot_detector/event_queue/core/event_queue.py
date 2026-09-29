from typing import Generic, Literal, Optional, TypeVar

from pydantic import BaseModel

from .interface import (
    QueueBackendConsumerProtocol,
    QueueBackendProducerProtocol,
    QueueBackendProtocol,
)
from .metrics import (
    GET_LATENCY,
    GET_MANY_OUTCOMES,
    MESSAGES_CONSUMED,
    MESSAGES_PRODUCED,
)

T = TypeVar("T", bound=BaseModel)


def _get_many_outcome(size: int, count: int) -> Literal["full", "partial", "empty"]:
    # kafka get_many can overshoot count when records span partitions,
    # so >= count is still a full batch
    if size <= 0:
        return "empty"
    if size < count:
        return "partial"
    return "full"


class QueueProducer(Generic[T]):
    """
    High-level Queue class used by the application.
    It relies on Dependency Injection to get the specific backend.

    Args:
        backend: the queue backend adapter.
        name: identity used for metrics labels (defaults to model name
            when created via QueueFactory).

    Example:
        config = InMemoryConfig(maxsize=50)
        adapter = InMemoryProducerAdapter(PlayerScraped, config=config)
        queue = QueueProducer[PlayerScraped](backend=adapter)
        await queue.put()
    """

    def __init__(self, backend: QueueBackendProducerProtocol, name: str = "unknown"):
        self._backend = backend
        self._name = name

    async def start(self):
        await self._backend.start()

    async def stop(self):
        await self._backend.stop()

    async def put(self, message: list[T]) -> Optional[Exception]:
        result = await self._backend.put(message)
        if result is None:
            MESSAGES_PRODUCED.labels(queue=self._name).inc(len(message))
        return result


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

    def __init__(self, backend: QueueBackendConsumerProtocol, name: str = "unknown"):
        self._backend = backend
        self._name = name

    async def start(self):
        await self._backend.start()

    async def stop(self):
        await self._backend.stop()

    async def get_one(self) -> Optional[T] | Exception:
        with GET_LATENCY.labels(queue=self._name, op="get_one").time():
            result = await self._backend.get_one()
        if isinstance(result, Exception):
            return result
        if result is not None:
            MESSAGES_CONSUMED.labels(queue=self._name).inc()
        return result

    async def get_many(self, count: int) -> list[T] | Exception:
        with GET_LATENCY.labels(queue=self._name, op="get_many").time():
            result = await self._backend.get_many(count)
        if isinstance(result, Exception):
            return result
        outcome = _get_many_outcome(size=len(result), count=count)
        GET_MANY_OUTCOMES.labels(queue=self._name, outcome=outcome).inc()
        MESSAGES_CONSUMED.labels(queue=self._name).inc(len(result))
        return result

    async def commit(self) -> Optional[Exception]:
        return await self._backend.commit()


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

    def __init__(self, backend: QueueBackendProtocol, name: str = "unknown"):
        self._backend = backend
        self._name = name
