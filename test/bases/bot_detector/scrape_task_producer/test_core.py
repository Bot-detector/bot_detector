import datetime

from bot_detector.scrape_task_producer.core import FetchParams, determine_fetch_params
from bot_detector.structs import PlayerStruct


def make_fetch_params(**kwargs) -> FetchParams:
    """Helper to construct FetchParams with default values overridden."""
    return FetchParams(
        days=kwargs.get("days", 7),
        confirmed_ban=kwargs.get("confirmed_ban", False),
        possible_ban=kwargs.get("possible_ban", False),
        player_id=kwargs.get("player_id", 0),
        limit=kwargs.get("limit", 1),
    )


def test_normal_fetch_with_results():
    players = [
        PlayerStruct(
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
    fetch_params = make_fetch_params()
    result = determine_fetch_params(fetch_params, players=players)
    assert result == FetchParams(
        days=7, confirmed_ban=False, possible_ban=False, player_id=42, limit=1
    )


def test_no_players_reduce_days():
    fetch_params = make_fetch_params(days=7)
    result = determine_fetch_params(fetch_params, players=[])
    assert result == FetchParams(
        days=6, confirmed_ban=False, possible_ban=False, player_id=0, limit=1
    )


def test_no_players_switch_to_confirmed_bans():
    fetch_params = make_fetch_params(days=1)
    result = determine_fetch_params(fetch_params, players=[])
    assert result == FetchParams(
        days=7, confirmed_ban=False, possible_ban=True, player_id=0, limit=1
    )


def test_no_players_reset():
    fetch_params = make_fetch_params(days=1, confirmed_ban=True, possible_ban=True)
    result = determine_fetch_params(fetch_params, players=[])
    assert result == FetchParams(
        days=7, confirmed_ban=False, possible_ban=False, player_id=0, limit=1
    )


def test_players_is_none():
    fetch_params = make_fetch_params()
    result = determine_fetch_params(fetch_params, players=None)
    assert result == fetch_params


def test_limit_greater_than_players():
    players = [
        PlayerStruct(
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
    fetch_params = make_fetch_params(limit=10)
    result = determine_fetch_params(fetch_params, players=players)
    assert result == FetchParams(
        days=6, confirmed_ban=False, possible_ban=False, player_id=0, limit=10
    )


def test_empty_players_with_confirmed_ban():
    fetch_params = make_fetch_params(days=8, confirmed_ban=True, possible_ban=True)
    result = determine_fetch_params(fetch_params, players=[], max_days=7)
    assert result == FetchParams(
        days=7, confirmed_ban=True, possible_ban=True, player_id=0, limit=1
    )


def test_days_decrement_normal():
    fetch_params = make_fetch_params(days=5)
    result = determine_fetch_params(fetch_params, players=[])
    assert result == FetchParams(
        days=4, confirmed_ban=False, possible_ban=False, player_id=0, limit=1
    )


def test_days_decrement_possible_ban():
    fetch_params = make_fetch_params(days=5, possible_ban=True)
    result = determine_fetch_params(fetch_params, players=[])
    assert result == FetchParams(
        days=4, confirmed_ban=False, possible_ban=True, player_id=0, limit=1
    )


def test_days_decrement_confirmed_ban():
    fetch_params = make_fetch_params(days=8, confirmed_ban=True, possible_ban=True)
    result = determine_fetch_params(fetch_params, players=[])
    assert result == FetchParams(
        days=7, confirmed_ban=True, possible_ban=True, player_id=0, limit=1
    )
