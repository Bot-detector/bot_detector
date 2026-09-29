import logging
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class ConnectionLike(Protocol):
    """Minimal contract the manager needs from a websocket."""

    @property
    def state(self) -> Any: ...

    async def accept(self) -> None: ...

    async def send_text(self, data: str) -> None: ...


class ConnectionManager:
    """Tracks active websocket connections, grouped by consumer group.

    Broadcasts go only to connections sharing the same group, so a keyed
    client's replayed stream does not flood anonymous clients.
    """

    def __init__(self) -> None:
        self.active_connections: dict[str, list[ConnectionLike]] = {}

    async def connect(self, websocket: ConnectionLike, group: str) -> None:
        await websocket.accept()
        websocket.state.group = group
        self.active_connections.setdefault(group, []).append(websocket)

    def disconnect(self, websocket: ConnectionLike) -> None:
        group = getattr(websocket.state, "group", None)
        if group is None:
            return
        connections = self.active_connections.get(group, [])
        if websocket in connections:
            connections.remove(websocket)
        if not connections:
            self.active_connections.pop(group, None)

    def count(self, group: str) -> int:
        return len(self.active_connections.get(group, []))

    async def send_personal_message(
        self, message: str, websocket: ConnectionLike
    ) -> None:
        await websocket.send_text(message)
