import datetime

from bot_detector.scrape_task_producer.core import determine_fetch_params
from bot_detector.structs import PlayerStruct


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
    result = determine_fetch_params(
        days=7, confirmed_ban=False, player_id=0, limit=1, players=players
    )
    assert result == (7, False, 42)


def test_no_players_reduce_days():
    result = determine_fetch_params(
        days=7, confirmed_ban=False, player_id=0, limit=1, players=[]
    )
    assert result == (6, False, 0)


def test_no_players_switch_to_confirmed_bans():
    result = determine_fetch_params(
        days=1, confirmed_ban=False, player_id=0, limit=1, players=[]
    )
    assert result == (7, True, 0)


def test_no_players_reset():
    result = determine_fetch_params(
        days=1, confirmed_ban=True, player_id=0, limit=1, players=[]
    )
    assert result == (7, False, 0)


def test_players_is_none():
    result = determine_fetch_params(
        days=7, confirmed_ban=False, player_id=0, limit=1, players=None
    )
    assert result == (7, False, 0)


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
    result = determine_fetch_params(
        days=7, confirmed_ban=False, player_id=0, limit=10, players=players
    )
    assert result == (6, False, 0)


def test_empty_players_with_confirmed_ban():
    result = determine_fetch_params(
        days=2, confirmed_ban=True, player_id=0, limit=1, players=[]
    )
    assert result == (1, True, 0)
