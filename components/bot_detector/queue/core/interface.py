from typing import Generic, Optional, Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class QueueBackendProducerProtocol(Generic[T], Protocol):
    """
    This defines the contract that ALL adapters must follow.
    The main Queue class refers to this, not the specific libraries.
    """

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def put(self, messages: list[T]) -> Optional[Exception]: ...


class QueueBackendConsumerProtocol(Generic[T], Protocol):
    """
    This defines the contract that ALL adapters must follow.
    The main Queue class refers to this, not the specific libraries.
    """

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def get_one(self) -> Optional[T] | Exception: ...

    async def get_many(self, count: int) -> list[T] | Exception: ...


class QueueBackendProtocol(
    QueueBackendProducerProtocol[T],
    QueueBackendConsumerProtocol[T],
    Protocol,
):
    """Combined protocol for producer and consumer operations."""

    ...
