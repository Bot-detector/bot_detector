import datetime
from unittest.mock import AsyncMock

import pytest
from bot_detector.event_queue.structs import ToScrapeBatchStruct
from bot_detector.scrape_task_producer.core import (
    FetchParams,
    Settings,
    determine_fetch_params,
    produce_players,
)
from bot_detector.structs import PlayerStruct
from pydantic import ValidationError


def make_fetch_params(**overrides) -> FetchParams:
    """Helper: start from sane defaults, apply any overrides."""
    params = FetchParams(
        days=overrides.get("days", 7),
        confirmed_ban=overrides.get("confirmed_ban", False),
        possible_ban=overrides.get("possible_ban", False),
        player_id=overrides.get("player_id", 0),
        limit=overrides.get("limit", 1),
        step=overrides.get("step", "normal"),
        done=overrides.get("done", False),
    )
    return params


def make_player(id: int = 1, name: str | None = None) -> PlayerStruct:
    """Minimal player factory with unique id."""
    now = datetime.datetime(2025, 1, 1, 12, 0, 0)
    return PlayerStruct(
        id=id,
        name=name or f"Player{id}",
        created_at=now,
        updated_at=now,
        possible_ban=False,
        confirmed_ban=False,
        confirmed_player=True,
        label_id=1,
        label_jagex=2,
    )


def test_returns_same_object_when_players_is_none():
    fp = make_fetch_params(
        days=3, possible_ban=True, confirmed_ban=True, player_id=5, limit=2
    )
    result = determine_fetch_params(fp, players=None)
    assert result is fp  # no mutation, same instance


def test_sets_player_id_to_last_when_full_page_of_results():
    players = [make_player(42)]
    fp = make_fetch_params(limit=1)
    result = determine_fetch_params(fp, players=players)
    assert result.player_id == 42
    # days and flags unchanged
    assert result.days == 7
    assert not result.possible_ban and not result.confirmed_ban


def test_resets_possible_ban_if_confirmed_ban_without_possible():
    # confirmed_ban=True but possible_ban=False → possible_ban forced True
    fp = make_fetch_params(confirmed_ban=True, possible_ban=False, step="confirmed_ban")
    result = determine_fetch_params(fp, players=[make_player()])
    assert result.possible_ban is True


@pytest.mark.parametrize("initial_days", [7, 5, 3])
def test_decrements_days_when_no_players_and_no_bans(initial_days):
    fp = make_fetch_params(days=initial_days, possible_ban=False, confirmed_ban=False)
    result = determine_fetch_params(fp, players=[])
    assert result.days == initial_days - 1
    assert result.player_id == 0


def test_decrements_days_when_no_players_and_possible_only_above_max():
    # default max_possible_ban_days=2, so days=5>2 → decrement
    fp = make_fetch_params(days=5, possible_ban=True, confirmed_ban=False)
    result = determine_fetch_params(fp, players=[])
    assert result.days == 4


def test_decrements_days_when_no_players_and_both_bans_above_max():
    # default max_confirmed_ban_days=7, so days=8>7 → decrement
    fp = make_fetch_params(days=8, possible_ban=True, confirmed_ban=True)
    result = determine_fetch_params(fp, players=[])
    assert result.days == 7


def test_switches_to_possible_ban_when_days_at_one_and_no_bans():
    fp = make_fetch_params(
        days=1,
        possible_ban=False,
        confirmed_ban=False,
        step="normal",
    )
    result = determine_fetch_params(fp, players=[], max_days=10)
    # days resets to max_days, possible_ban flips on
    assert result.days == 10
    assert result.step == "possible_ban"


def test_advances_to_confirmed_ban_when_possible_cycle_exhausted():
    # days <= max_possible_ban_days (default 2), possible_ban=True, confirmed_ban=False
    fp = make_fetch_params(
        days=2,
        step="possible_ban",
    )
    result = determine_fetch_params(fp, players=[], max_days=9)
    assert result.days == 9
    assert result.step == "confirmed_ban"


def test_full_reset_after_confirmed_cycle_exhausted():
    # days <= max_confirmed_ban_days (default 7), both bans True
    fp = make_fetch_params(
        days=7,
        step="confirmed_ban",
    )
    result = determine_fetch_params(
        fp,
        players=[],
        max_days=11,
        max_possible_ban_days=3,
        max_confirmed_ban_days=7,
    )
    assert result.step == "normal"
    assert result.days == 11


def make_players(count: int, start_id: int = 1) -> list[PlayerStruct]:
    return [make_player(id=start_id + i) for i in range(count)]


def _captured_batches(queue) -> list[ToScrapeBatchStruct]:
    (batches,) = queue.put.await_args.args
    return batches


@pytest.mark.asyncio
async def test_produce_players_packs_full_page_into_one_batch():
    queue = AsyncMock()
    queue.put = AsyncMock(return_value=None)

    await produce_players(players=make_players(10), player_queue=queue, batch_size=10)

    batches = _captured_batches(queue)
    assert len(batches) == 1
    assert isinstance(batches[0], ToScrapeBatchStruct)
    assert len(batches[0].players) == 10
    # version 2 marks the batched payload; version 1 stays legacy
    assert batches[0].metadata.version == 2
    assert batches[0].metadata.source == "scrape_task_producer"


@pytest.mark.asyncio
async def test_produce_players_chunks_partial_final_batch():
    queue = AsyncMock()
    queue.put = AsyncMock(return_value=None)

    await produce_players(players=make_players(25), player_queue=queue, batch_size=10)

    batches = _captured_batches(queue)
    assert [len(batch.players) for batch in batches] == [10, 10, 5]
    # every player lands exactly once, in order
    ids = [player.id for batch in batches for player in batch.players]
    assert ids == list(range(1, 26))


@pytest.mark.asyncio
async def test_produce_players_filters_long_names_before_chunking():
    queue = AsyncMock()
    queue.put = AsyncMock(return_value=None)
    players = make_players(5) + [make_player(id=99, name="a-very-long-player-name")]

    await produce_players(players=players, player_queue=queue, batch_size=10)

    batches = _captured_batches(queue)
    assert len(batches) == 1
    assert [player.id for player in batches[0].players] == [1, 2, 3, 4, 5]


@pytest.mark.asyncio
async def test_produce_players_skips_put_when_no_eligible_players():
    queue = AsyncMock()
    queue.put = AsyncMock(return_value=None)
    players = [make_player(id=1, name="a-very-long-player-name")]

    await produce_players(players=players, player_queue=queue, batch_size=10)

    queue.put.assert_not_awaited()


def test_batch_size_defaults_to_ten():
    assert Settings().TO_SCRAPE_BATCH_SIZE == 10


def test_batch_size_is_configurable_via_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TO_SCRAPE_BATCH_SIZE", "25")

    assert Settings().TO_SCRAPE_BATCH_SIZE == 25


@pytest.mark.parametrize("invalid", ["0", "-3"])
def test_batch_size_rejects_zero_and_negative(
    monkeypatch: pytest.MonkeyPatch, invalid: str
):
    monkeypatch.setenv("TO_SCRAPE_BATCH_SIZE", invalid)

    with pytest.raises(ValidationError):
        Settings()
