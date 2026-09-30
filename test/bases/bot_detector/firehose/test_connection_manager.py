import asyncio

import pytest
from bot_detector.firehose.app.connection_manager import (
    SEND_TIMEOUT_S,
    ConnectionGoneError,
    ConnectionManager,
)


class FakeWebSocket:
    def __init__(self, hang_send: bool = False, hang_close: bool = False):
        self.accepted = False
        self.sent: list[str] = []
        self.closed: tuple | None = None
        self._hang_send = hang_send
        self._hang_close = hang_close

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, data: str) -> None:
        if self._hang_send:
            # parks longer than SEND_TIMEOUT_S
            await asyncio.sleep(SEND_TIMEOUT_S + 5)
        self.sent.append(data)

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        if self._hang_close:
            # parks longer than SEND_TIMEOUT_S: a close handshake
            # flushing a send buffer the peer stopped reading
            await asyncio.sleep(SEND_TIMEOUT_S + 5)
        self.closed = (code, reason)


@pytest.fixture
def manager() -> ConnectionManager:
    return ConnectionManager()


@pytest.mark.asyncio
async def test_connect_accepts_registers_and_returns_id(manager: ConnectionManager):
    ws = FakeWebSocket()

    conn_id = await manager.connect(websocket=ws, group="g")

    assert ws.accepted is True
    assert isinstance(conn_id, str) and conn_id
    assert manager.group(conn_id) == "g"
    assert manager.count(group="g") == 1
    assert manager.has_connections(group="g") is True


@pytest.mark.asyncio
async def test_send_delivers_to_the_registered_socket(manager: ConnectionManager):
    ws = FakeWebSocket()
    conn_id = await manager.connect(websocket=ws, group="g")

    await manager.send(conn_id, "hello")

    assert ws.sent == ["hello"]


@pytest.mark.asyncio
async def test_send_unknown_id_raises(manager: ConnectionManager):
    with pytest.raises(ConnectionGoneError):
        await manager.send("missing", "hello")


@pytest.mark.asyncio
async def test_send_timeout_raises_and_socket_must_be_closed(
    manager: ConnectionManager,
):
    ws = FakeWebSocket(hang_send=True)
    conn_id = await manager.connect(websocket=ws, group="g")

    with pytest.raises(asyncio.TimeoutError):
        await manager.send(conn_id, "hello")

    # a cancelled send can leave a partial frame: close, never retry
    await manager.close(conn_id, code=1013, reason="inbox full")

    assert ws.closed == (1013, "inbox full")
    assert manager.count(group="g") == 0


@pytest.mark.asyncio
async def test_close_is_idempotent(manager: ConnectionManager):
    ws = FakeWebSocket()
    conn_id = await manager.connect(websocket=ws, group="g")

    await manager.close(conn_id, code=1000, reason="bye")
    await manager.close(conn_id, code=1000, reason="bye")

    assert ws.closed == (1000, "bye")
    assert manager.count(group="g") == 0


@pytest.mark.asyncio
async def test_close_is_bounded_when_the_peer_stops_reading(
    manager: ConnectionManager,
):
    ws = FakeWebSocket(hang_close=True)
    conn_id = await manager.connect(websocket=ws, group="g")

    t0 = asyncio.get_running_loop().time()
    # must not raise and must not park past SEND_TIMEOUT_S: a hung
    # close would keep the route from its cleanup forever
    await manager.close(conn_id, code=1013, reason="inbox full")
    elapsed = asyncio.get_running_loop().time() - t0

    assert elapsed < SEND_TIMEOUT_S + 1
    assert manager.count(group="g") == 0


@pytest.mark.asyncio
async def test_disconnect_forgets_without_touching_the_socket(
    manager: ConnectionManager,
):
    ws = FakeWebSocket()
    conn_id = await manager.connect(websocket=ws, group="g")

    manager.disconnect(conn_id)

    assert manager.count(group="g") == 0
    assert ws.closed is None
    # idempotent
    manager.disconnect(conn_id)


@pytest.mark.asyncio
async def test_groups_are_independent(manager: ConnectionManager):
    await manager.connect(websocket=FakeWebSocket(), group="g1")
    await manager.connect(websocket=FakeWebSocket(), group="g2")

    assert manager.count(group="g1") == 1
    assert manager.count(group="g2") == 1
    assert manager.has_connections(group="g1") is True
    assert manager.has_connections(group="g3") is False
