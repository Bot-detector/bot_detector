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
async def test_send_personal_message_targets_one_connection(manager: ConnectionManager):
    ws_a = FakeWebSocket()
    ws_b = FakeWebSocket()
    await manager.connect(websocket=ws_a, group="firehose-anonymous")
    await manager.connect(websocket=ws_b, group="firehose-anonymous")

    await manager.send_personal_message(message="hello", websocket=ws_b)

    assert ws_a.sent == []
    assert ws_b.sent == ["hello"]


@pytest.mark.asyncio
async def test_disconnect_removes_connection(manager: ConnectionManager):
    ws = FakeWebSocket()
    await manager.connect(websocket=ws, group="g")

    manager.disconnect(websocket=ws)

    assert manager.count(group="g") == 0
    # idempotent
    manager.disconnect(websocket=ws)
    assert manager.count(group="g") == 0
