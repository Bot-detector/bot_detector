import datetime

from bot_detector.scrape_task_producer.core import (
    determine_fetch_params,
)
from bot_detector.structs import PlayerStruct


def test_determine_fetch_params():
    # Case 1: Normal fetch with results, should move to next player_id
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
