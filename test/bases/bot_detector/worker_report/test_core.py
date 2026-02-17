import pytest
from bot_detector.worker_report import main as core


class _FakeQueue:
    async def start(self):
        return None


class _FakeEngine:
    async def dispose(self):
        return None


@pytest.mark.asyncio
async def test_main_uses_reports_queue_for_consumer_and_producer(monkeypatch):
    captured = {}

    def _queue_factory(*args, **kwargs):
        q = _FakeQueue()
        captured["queue"] = q
        return q

    async def _consume_many_task(**kwargs):
        captured["consumer"] = kwargs["report_consumer"]
        return None

    async def _error_task(**kwargs):
        captured["producer"] = kwargs["report_producer"]
        return None

    monkeypatch.setattr(core, "DBSettings", lambda: object())
    monkeypatch.setattr(
        core.db, "get_session_factory", lambda SETTINGS: (object(), _FakeEngine())
    )
    monkeypatch.setattr(
        core, "KafkaSettings", lambda: type("S", (), {"KAFKA_BOOTSTRAP_SERVERS": "x"})()
    )
    monkeypatch.setattr(core, "ReportsToInsertQueue", _queue_factory)
    monkeypatch.setattr(core, "consume_many_task", _consume_many_task)
    monkeypatch.setattr(core, "error_task", _error_task)

    await core.main()

    assert captured["consumer"] is captured["queue"]
    assert captured["producer"] is captured["queue"]
