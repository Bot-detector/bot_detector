import os
from datetime import datetime, timedelta

import pytest
from bot_detector.runemetrics_api.core import RuneMetricsError, RuneMetricsResponse
from bot_detector.runemetrics_scraper import core
from bot_detector.structs import PlayerStruct
from pydantic import BaseModel

os.environ["ENVIRONMENT"] = "test"


class DummyError(BaseModel):
    error: str
    loggedIn: bool = False


@pytest.fixture
def player_struct():
    return PlayerStruct(
        id=1,
        name="test_player",
        created_at=datetime.now() - timedelta(days=1),
        updated_at=None,
        possible_ban=False,
        confirmed_ban=False,
        confirmed_player=False,
        label_id=0,
        label_jagex=0,
        ironman=None,
        hardcore_ironman=None,
        ultimate_ironman=None,
        normalized_name=None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error_value,expected_label",
    [
        (None, 0),
        ("NO_PROFILE", 1),
        ("NOT_A_MEMBER", 2),
        ("PROFILE_PRIVATE", 3),
        ("SOMETHING_ELSE", 0),
    ],
)
async def test_update_player(player_struct: PlayerStruct, error_value, expected_label):
    runemetrics_response = RuneMetricsResponse()

    if error_value is not None:
        runemetrics_response.error = RuneMetricsError(
            error=error_value,
            loggedIn=False,
        )

    updated = await core.update_player(
        player_data=player_struct.model_copy(),
        runemetrics_response=runemetrics_response,
    )

    assert updated.label_jagex == expected_label
    assert updated.possible_ban == 1
    assert updated.confirmed_player == 0
    assert isinstance(updated.updated_at, datetime)


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
        return ["a", "b"]


@pytest.mark.asyncio
async def test_main_uses_players_not_found_queue_for_consumer_and_producer(monkeypatch):
    captured = {}

    def _queue_factory(*args, **kwargs):
        q = _FakeQueue()
        captured["queue"] = q
        return q

    async def _work(**kwargs):
        captured["consumer"] = kwargs["player_nf_consumer"]
        captured["producer"] = kwargs["player_nf_producer"]
        return None

    monkeypatch.setattr(
        core, "KafkaSettings", lambda: type("S", (), {"KAFKA_BOOTSTRAP_SERVERS": "x"})()
    )
    monkeypatch.setattr(
        core,
        "ProxySettings",
        lambda: type("PS", (), {"PROXY_API_KEY": "x", "MAX_CALLS": 1, "INTERVAL": 1})(),
    )
    monkeypatch.setattr(core, "PlayersNotFoundQueue", _queue_factory)
    monkeypatch.setattr(core, "PlayersScrapedProducer", lambda *a, **k: _FakeProducer())
    monkeypatch.setattr(core, "ProxyManager", _FakeProxyManager)
    monkeypatch.setattr(core, "work", _work)

    await core.main()

    assert captured["consumer"] is captured["queue"]
    assert captured["producer"] is captured["queue"]
