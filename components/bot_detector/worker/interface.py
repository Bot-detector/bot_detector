from typing import Generic, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@runtime_checkable
class WorkerInterface(Protocol, Generic[T]):
    """Protocol for worker implementations."""
    __slots__ = ()

    async def start(self) -> None: ...
    async def stop(self) -> None: ...

    async def on_message(self, message: T) -> bool: ...
    async def on_message_batch(self, messages: list[T]) -> bool: ...
