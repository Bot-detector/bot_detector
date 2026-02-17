import pytest
from bot_detector.hiscore_scraper import core


class _FakeQueue:
    async def start(self):
        return None

    async def consume_one(self):
        return None, "empty"

    async def produce_one(self, *args, **kwargs):
        return None


class _FakeProducer:
    async def start(self):
        return None


class _FakeProxyManager:
    def __init__(self, *args, **kwargs):
        pass

    async def fetch_proxies(self):
        return ["a"]


@pytest.mark.asyncio
async def test_main_uses_players_to_scrape_queue_for_consumer_and_producer(monkeypatch):
    captured = {}

    def _queue_factory(*args, **kwargs):
        q = _FakeQueue()
        captured["queue"] = q
        return q

    async def _work(**kwargs):
        captured["consumer"] = kwargs["player_ts_consumer"]
        captured["producer"] = kwargs["player_ts_producer"]
        return None

    monkeypatch.setattr(
        core, "KafkaSettings", lambda: type("S", (), {"KAFKA_BOOTSTRAP_SERVERS": "x"})()
    )
    monkeypatch.setattr(
        core,
        "ProxySettings",
        lambda: type("PS", (), {"PROXY_API_KEY": "x", "MAX_CALLS": 1, "INTERVAL": 1})(),
    )
    monkeypatch.setattr(core, "PlayersToScrapeQueue", _queue_factory)
    monkeypatch.setattr(
        core, "PlayersNotFoundProducer", lambda *a, **k: _FakeProducer()
    )
    monkeypatch.setattr(core, "PlayersScrapedProducer", lambda *a, **k: _FakeProducer())
    monkeypatch.setattr(core, "ProxyManager", _FakeProxyManager)
    monkeypatch.setattr(core, "work", _work)

    await core.main()

    assert captured["consumer"] is captured["queue"]
    assert captured["producer"] is captured["queue"]
