import pytest
from bot_detector.worker_hiscore import core


class _FakeQueue:
    def __init__(self, *args, **kwargs):
        self.started = False

    async def start(self):
        self.started = True

    async def produce_one(self, *args, **kwargs):
        return None

    async def consume_many(self, *args, **kwargs):
        return [], []

    async def commit(self):
        return None


class _FakeProducer:
    async def start(self):
        return None


class _FakeEngine:
    async def dispose(self):
        return None


@pytest.mark.asyncio
async def test_main_uses_players_scraped_queue_for_consumer_and_producer(monkeypatch):
    captured = {}

    def _queue_factory(*args, **kwargs):
        queue = _FakeQueue()
        captured["queue"] = queue
        return queue

    async def _consume_many_task(**kwargs):
        captured["consumer"] = kwargs["player_sc_consumer"]
        captured["producer"] = kwargs["player_sc_producer"]
        return None

    monkeypatch.setattr(core, "DBSettings", lambda: object())
    monkeypatch.setattr(
        core.db, "get_session_factory", lambda SETTINGS: (object(), _FakeEngine())
    )
    monkeypatch.setattr(
        core, "KafkaSettings", lambda: type("S", (), {"KAFKA_BOOTSTRAP_SERVERS": "x"})()
    )
    monkeypatch.setattr(core, "PlayersScrapedQueue", _queue_factory)
    monkeypatch.setattr(core, "DataToPredictProducer", lambda *a, **k: _FakeProducer())
    monkeypatch.setattr(core, "consume_many_task", _consume_many_task)

    await core.main()

    assert captured["consumer"] is captured["queue"]
    assert captured["producer"] is captured["queue"]
