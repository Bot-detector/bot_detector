import asyncio
import logging
import uuid
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger(__name__)

# a send that cannot complete within this window marks the connection
# dead: the caller must close it, never send on it again (a cancelled
# send can leave a partial frame on the wire)
SEND_TIMEOUT_S = 2.0


class WebsocketLike(Protocol):
    """Minimal contract the manager needs from a websocket."""

    async def accept(self) -> None: ...

    async def send_text(self, data: str) -> None: ...

    async def close(self, code: int = 1000, reason: str | None = None) -> None: ...


@dataclass
class Connection:
    """A registered websocket and the consumer group it joined."""

    id: str
    websocket: WebsocketLike
    group: str


class ConnectionManager:
    """The interface between the firehose and websockets.

    Owns the connection registry (id -> websocket, grouped by consumer
    group) and every socket operation: accept, bounded send, close.
    Callers never touch the websocket itself; a failed or timed-out send
    raises, and the caller closes the connection via `close`.
    """

    def __init__(self) -> None:
        self._connections: dict[str, Connection] = {}

    async def connect(self, websocket: WebsocketLike, group: str) -> str:
        """Accept the socket, register it and return its connection id."""
        await websocket.accept()
        conn_id = uuid.uuid4().hex
        self._connections[conn_id] = Connection(
            id=conn_id, websocket=websocket, group=group
        )
        return conn_id

    def disconnect(self, conn_id: str) -> None:
        """Forget a connection without touching the socket."""
        self._connections.pop(conn_id, None)

    async def send(self, conn_id: str, payload: str) -> None:
        """Send to one connection; raises when it is gone or too slow.

        A timeout cancels the in-flight send: the socket is unusable
        afterwards, so the caller must close it (kick), never retry.
        """
        connection = self._connections.get(conn_id)
        if connection is None:
            raise ConnectionGoneError(conn_id)
        await asyncio.wait_for(
            connection.websocket.send_text(payload), timeout=SEND_TIMEOUT_S
        )

    async def close(self, conn_id: str, code: int, reason: str) -> None:
        """Close the socket and drop the registration (idempotent).

        Bounded: the close handshake flushes the same send buffer that
        backpressure kicked the connection for (a peer that stopped
        reading), so without a cap the route parks forever in close,
        never unsubscribes, and leaks the inbox. On timeout the socket
        is abandoned - the registration is already gone, so the route
        can always finish its cleanup.
        """
        connection = self._connections.pop(conn_id, None)
        if connection is None:
            return
        try:
            await asyncio.wait_for(
                connection.websocket.close(code=code, reason=reason),
                timeout=SEND_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            logger.warning(f"close abandoned (peer stopped reading): {conn_id}")
        except Exception:
            logger.debug(f"close failed for connection={conn_id}")

    def group(self, conn_id: str) -> str | None:
        connection = self._connections.get(conn_id)
        return connection.group if connection else None

    def count(self, group: str) -> int:
        return sum(1 for c in self._connections.values() if c.group == group)

    def has_connections(self, group: str) -> bool:
        return self.count(group) > 0


class ConnectionGoneError(Exception):
    """The connection id is not registered (already disconnected)."""

    def __init__(self, conn_id: str):
        self.conn_id = conn_id
        super().__init__(f"connection gone: {conn_id}")
