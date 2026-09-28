from typing import Protocol, runtime_checkable

from bot_detector.firehose.app.group_stream.structs import Inbox
from pydantic import BaseModel


@runtime_checkable
class GroupStreamProtocol(Protocol):
    """Contract the api and consumer manager need from a stream."""

    topic: str
    group: str
    anonymous: bool
    type: str
    count: int

    def subscribe(self, name: str | None = None) -> Inbox | None: ...

    def unsubscribe(self, inbox: Inbox | None) -> None: ...

    async def get(self) -> BaseModel | Exception: ...

    async def stop(self) -> None: ...
