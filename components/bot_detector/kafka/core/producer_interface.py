from typing import Any, Generic, Optional, Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel, contravariant=True)


class ProducerInterface(Protocol, Generic[T]):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def get_producer(self) -> Any: ...
    async def produce_one(
        self,
        message: T,
        topic: Optional[str] = None,
        partition_key: Optional[bytes] = None,
        max_retries: int = 5,
    ): ...
