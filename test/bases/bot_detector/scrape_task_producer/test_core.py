import datetime

import pytest
from bot_detector.scrape_task_producer.core import FetchParams, determine_fetch_params
from bot_detector.player.structs import PlayerStruct


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


def make_player(id: int = 1) -> PlayerStruct:
    """Minimal player factory with unique id."""
    now = datetime.datetime(2025, 1, 1, 12, 0, 0)
    return PlayerStruct(
        id=id,
        name=f"Player{id}",
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
