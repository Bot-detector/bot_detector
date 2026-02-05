from typing import Generic, Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class WorkerInterface(Protocol):  # pragma: no cover
    async def start(self) -> None: ...
    async def stop(self) -> None: ...


class ConsumerWorkerInterface(WorkerInterface, Generic[T]):  # pragma: no cover
    async def on_message(self, message: T) -> Exception | None: ...
    async def on_message_batch(self, messages: list[T]) -> Exception | None: ...


class ProducerWorkerInterface(WorkerInterface, Generic[T]):  # pragma: no cover
    async def build_messages(self) -> list[T] | Exception | None: ...
