import asyncio
import datetime

import pytest
from bot_detector.database.structs import PlayerStruct
from bot_detector.schema import Player
from bot_detector.scrape_task_producer.core import (
    determine_fetch_params,
)


# --- Dummy Database Session for Testing fetch_players ---
class DummyResult:
    def scalars(self):
        return self

    def all(self):
        return [
            {
                "id": 1,
                "name": "Dummy Player",
                "created_at": datetime.datetime(2025, 1, 1, 12, 0, 0),
                "updated_at": datetime.datetime(2025, 1, 2, 12, 0, 0),
                "possible_ban": False,
                "confirmed_ban": False,
                "confirmed_player": True,
                "label_id": 10,
                "label_jagex": 20,
            }
        ]


class DummySession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, tb):
        pass

    async def execute(self, sql, params):
        return DummyResult()


class DummySessionMaker:
    def __call__(self):
        return DummySession()


# --- determine_fetch_params Logic ---
@pytest.mark.asyncio
async def test_determine_fetch_params():
    # Case 1: Normal fetch with results, should move to next player_id
    players = [
        Player(
            id=42,
            name="Test Player",
            created_at=datetime.datetime(2025, 1, 1, 12, 0, 0),
            updated_at=datetime.datetime(2025, 1, 2, 12, 0, 0),
            possible_ban=False,
            confirmed_ban=False,
            confirmed_player=True,
            label_id=1,
            label_jagex=2,
        )
    ]
    result = await determine_fetch_params(
        days=7, confirmed_ban=False, player_id=0, limit=1, players=players
    )
    assert result == (7, False, 42, 1)

    # Case 2: No players left, reduce days
    result = await determine_fetch_params(
        days=7, confirmed_ban=False, player_id=0, limit=1, players=[]
    )
    assert result == (6, False, 0, 1)

    # Case 3: No players left, and days = 1, switch to confirmed_ban=True
    result = await determine_fetch_params(
        days=1, confirmed_ban=False, player_id=0, limit=1, players=[]
    )
    assert result == (7, True, 0, 1)

    # Case 4: No players left, and days = 1 with confirmed_ban=True, reset
    result = await determine_fetch_params(
        days=1, confirmed_ban=True, player_id=0, limit=1, players=[]
    )
    assert result == (7, False, 0, 1)


# Test that days decrement properly when no players are returned.
@pytest.mark.asyncio
async def test_day_decrement():
    days, confirmed_ban, player_id, limit = await determine_fetch_params(
        players=[], player_id=0, confirmed_ban=False, days=5, limit=10
    )
    assert (days, confirmed_ban, player_id, limit) == (4, False, 0, 10)


@pytest.mark.asyncio
async def test_day_decrement_day_one_cb_false():
    days, confirmed_ban, player_id, limit = await determine_fetch_params(
        players=[], player_id=0, confirmed_ban=False, days=1, limit=10, max_days=7
    )
    assert (days, confirmed_ban, player_id, limit) == (7, True, 0, 10)


@pytest.mark.asyncio
async def test_day_decrement_day_zero_cb_false():
    days, confirmed_ban, player_id, limit = await determine_fetch_params(
        players=[], player_id=0, confirmed_ban=False, days=0, limit=10, max_days=7
    )
    assert (days, confirmed_ban, player_id, limit) == (7, True, 0, 10)


@pytest.mark.asyncio
async def test_day_decrement_day_one_cb_true():
    days, confirmed_ban, player_id, limit = await determine_fetch_params(
        players=[], player_id=0, confirmed_ban=True, days=1, limit=10, max_days=7
    )
    assert (days, confirmed_ban, player_id, limit) == (7, False, 0, 10)


@pytest.mark.asyncio
async def test_day_decrement_day_zero_cb_true():
    days, confirmed_ban, player_id, limit = await determine_fetch_params(
        players=[], player_id=0, confirmed_ban=True, days=0, limit=10, max_days=7
    )
    assert days == 7
    err = f"Expected confirmed_ban to be False, got {confirmed_ban=}"
    assert confirmed_ban is False, err


# Test that the fetch logic sleeps when reaching the reset condition (days = 1 and confirmed_ban = True).
@pytest.mark.asyncio
async def test_reset_wait(monkeypatch):
    called = {"slept": False}

    async def fake_sleep(secs):
        called["slept"] = True
        assert secs == 60

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    await determine_fetch_params(
        days=1, confirmed_ban=True, player_id=0, limit=10, players=[]
    )
    assert called["slept"] is True
