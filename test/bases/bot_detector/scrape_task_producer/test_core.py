import datetime
from asyncio import Queue

import pytest
from bot_detector.schema import Player
from bot_detector.scrape_task_producer.core import (
    determine_fetch_params,
    fetch_players,
    put_players_in_queue,
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


# --- Test fetch_players ---


@pytest.mark.asyncio
async def test_fetch_players():
    dummy_session = DummySessionMaker()

    players = await fetch_players(
        async_session=dummy_session,
        days=7,
        confirmed_ban=False,
        player_id=0,
        limit=10_000,
    )

    assert len(players) == 1
    player = players[0]
    assert isinstance(player, Player)
    assert player.id == 1
    assert player.name == "Dummy Player"
    assert player.label_jagex == 20


# --- Test put_players_in_queue ---


@pytest.mark.asyncio
async def test_put_players_in_queue():
    queue = Queue()

    valid_player = Player(
        id=1,
        name="Test Player",
        created_at=datetime.datetime(2025, 1, 1, 12, 0, 0),
        updated_at=datetime.datetime(2025, 1, 2, 12, 0, 0),
        possible_ban=False,
        confirmed_ban=False,
        confirmed_player=True,
        label_id=1,
        label_jagex=1,
    )
    invalid_player = "not a player"

    players = [valid_player, invalid_player]
    await put_players_in_queue(players, queue)

    # Validate that only the valid player got added
    dumped_valid = valid_player.model_dump(mode="json")
    results = []
    while not queue.empty():
        results.append(await queue.get())

    assert dumped_valid in results
    assert len(results) == 1


# --- Test determine_fetch_params ---


def test_determine_fetch_params():
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
    result = determine_fetch_params(
        days=7, confirmed_ban=False, player_id=0, limit=1, players=players
    )
    assert result == (7, False, 42, 1)

    # Case 2: No players left, reduce days
    result = determine_fetch_params(
        days=7, confirmed_ban=False, player_id=0, limit=1, players=[]
    )
    assert result == (6, False, 0, 1)

    # Case 3: No players left, and days = 1, switch to confirmed_ban=True
    result = determine_fetch_params(
        days=1, confirmed_ban=False, player_id=0, limit=1, players=[]
    )
    assert result == (7, True, 0, 1)

    # Case 4: No players left, and days = 1 with confirmed_ban=True, reset
    result = determine_fetch_params(
        days=1, confirmed_ban=True, player_id=0, limit=1, players=[]
    )
    assert result == (7, False, 0, 1)
