from typing import Generic, Optional, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@runtime_checkable
class QueueBackendProducerProtocol(Generic[T], Protocol):
    """
    This defines the contract that ALL adapters must follow.
    The main Queue class refers to this, not the specific libraries.
    """

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def put(self, messages: list[T]) -> Optional[Exception]: ...


@runtime_checkable
class QueueBackendConsumerProtocol(Generic[T], Protocol):
    """
    This defines the contract that ALL adapters must follow.
    The main Queue class refers to this, not the specific libraries.
    """

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def get_one(self) -> Optional[T] | Exception: ...

    async def get_many(self, count: int) -> list[T] | Exception: ...

    async def commit(self) -> Optional[Exception]: ...

    async def lag(self) -> int: ...


@runtime_checkable
class QueueBackendProtocol(
    QueueBackendProducerProtocol[T],
    QueueBackendConsumerProtocol[T],
    Protocol,
):
    """Combined protocol for producer and consumer operations."""

    ...
