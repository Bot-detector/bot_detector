from typing import Any, Protocol, runtime_checkable

from bot_detector.event_queue.core import QueueConsumer
from bot_detector.firehose.app.auth.auth import AuthUser


@runtime_checkable
class QueueRepoProtocol(Protocol):
    def resolve_consumer_group(self, user: AuthUser, topic: str) -> str: ...

    def create_consumer(
        self, user: AuthUser, topic: str
    ) -> QueueConsumer[Any] | Exception: ...
