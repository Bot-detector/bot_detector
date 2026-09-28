import asyncio
from typing import Protocol, runtime_checkable

from pydantic import BaseModel


@runtime_checkable
class GroupStreamProtocol(Protocol):
    """Contract the api and consumer manager need from a stream."""

    topic: str
    group: str
    anonymous: bool
    type: str
    count: int

    def subscribe(self) -> asyncio.Queue | None: ...

    def unsubscribe(self, inbox: asyncio.Queue | None) -> None: ...

    async def get(self) -> BaseModel | Exception: ...

    async def stop(self) -> None: ...
