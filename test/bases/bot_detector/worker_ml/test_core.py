import os

import pytest

os.environ.setdefault("BASE_URL", "http://localhost")
os.environ.setdefault("MODEL_NAME", "dummy")

from bot_detector.worker_ml import core


class _FakeQueue:
    async def start(self):
        return None

    async def stop(self):
        return None


class _FakeSession:
    async def close(self):
        return None


class _FakeEngine:
    async def dispose(self):
        return None


@pytest.mark.asyncio
async def test_main_uses_data_to_predict_queue_for_consumer_and_producer(monkeypatch):
    captured = {}

    def _queue_factory(*args, **kwargs):
        q = _FakeQueue()
        captured["queue"] = q
        return q

    async def _consume_data_to_predict(**kwargs):
        captured["consumer"] = kwargs["data_to_predict_consumer"]
        captured["producer"] = kwargs["data_to_predict_producer"]
        return None

    monkeypatch.setattr(
        core, "KafkaSettings", lambda: type("S", (), {"KAFKA_BOOTSTRAP_SERVERS": "x"})()
    )
    monkeypatch.setattr(core, "DataToPredictQueue", _queue_factory)
    monkeypatch.setattr(core, "DBSettings", lambda: object())
    monkeypatch.setattr(
        core, "get_session_factory", lambda SETTINGS: (object(), _FakeEngine())
    )
    monkeypatch.setattr(core.aiohttp, "ClientSession", lambda: _FakeSession())
    monkeypatch.setattr(core, "MLApiClient", lambda base_url, session: object())
    monkeypatch.setattr(core, "consume_data_to_predict", _consume_data_to_predict)

    await core.main()

    assert captured["consumer"] is captured["queue"]
    assert captured["producer"] is captured["queue"]
