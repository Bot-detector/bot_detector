from types import SimpleNamespace

import pytest
from bot_detector.firehose.app.connection_manager import ConnectionManager


class FakeWebSocket:
    def __init__(self, fail_send: bool = False):
        self.state = SimpleNamespace()
        self.accepted = False
        self.sent: list[str] = []
        self._fail_send = fail_send

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, data: str) -> None:
        if self._fail_send:
            raise RuntimeError("socket closed")
        self.sent.append(data)


@pytest.fixture
def manager() -> ConnectionManager:
    return ConnectionManager()


@pytest.mark.asyncio
async def test_connect_accepts_and_groups(manager: ConnectionManager):
    ws = FakeWebSocket()
    await manager.connect(websocket=ws, group="firehose-anonymous")

    assert ws.accepted is True
    assert manager.count(group="firehose-anonymous") == 1
    assert ws.state.group == "firehose-anonymous"


@pytest.mark.asyncio
async def test_broadcast_reaches_only_same_group(manager: ConnectionManager):
    ws_anon = FakeWebSocket()
    ws_keyed = FakeWebSocket()
    await manager.connect(websocket=ws_anon, group="firehose-anonymous")
    await manager.connect(websocket=ws_keyed, group="firehose-keyed")

    await manager.broadcast(message="hello", group="firehose-anonymous")

    assert ws_anon.sent == ["hello"]
    assert ws_keyed.sent == []


@pytest.mark.asyncio
async def test_broadcast_drops_failing_connections(manager: ConnectionManager):
    ws_good = FakeWebSocket()
    ws_bad = FakeWebSocket(fail_send=True)
    await manager.connect(websocket=ws_good, group="g")
    await manager.connect(websocket=ws_bad, group="g")

    await manager.broadcast(message="hello", group="g")

    assert ws_good.sent == ["hello"]
    assert manager.count(group="g") == 1


@pytest.mark.asyncio
async def test_disconnect_removes_connection(manager: ConnectionManager):
    ws = FakeWebSocket()
    await manager.connect(websocket=ws, group="g")

    manager.disconnect(websocket=ws)

    assert manager.count(group="g") == 0
    # idempotent
    manager.disconnect(websocket=ws)
    assert manager.count(group="g") == 0
