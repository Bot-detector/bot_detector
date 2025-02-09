from datetime import datetime

import pytest
from bot_detector.hiscore_worker.worker import (
    extract_data_from_batch,  # adjust "your_module" as needed
)
from bot_detector.schema import (
    MetaData,
    Player,
    ScraperData,
    ScraperHiscoreData,
)


@pytest.fixture
def dummy_metadata():
    return MetaData(version=1, source="test")


def test_extract_data_from_batch(dummy_metadata):
    # Define datetimes for the test cases.
    # For Player 1:
    dt1 = datetime(2023, 1, 5, 12, 0, 0)  # Message 1: first hiscore (week 1)
    dt2 = datetime(2023, 1, 6, 12, 0, 0)  # Message 2: update player (no hiscore)
    dt3 = datetime(
        2023, 1, 5, 15, 0, 0
    )  # Message 3: hiscore provided (same week as dt1, but later than dt1)
    dt4 = datetime(2023, 1, 9, 12, 0, 0)  # Message 4: hiscore provided (new week)

    # For Player 2:
    dt5 = datetime(2023, 2, 1, 12, 0, 0)  # Message A: hiscore provided (week X)
    dt6 = datetime(
        2023, 2, 1, 10, 0, 0
    )  # Message B: hiscore provided, but older than dt5
    dt7 = datetime(2023, 2, 2, 12, 0, 0)  # Message C: update player (no hiscore)

    # For Player 3:
    dt8 = datetime(2023, 3, 1, 12, 0, 0)  # Single message, no hiscore

    # Create Player messages.
    # Note: Although the Player model defines updated_at as a string or None,
    # in these tests we provide datetime objects. Pydantic will convert these
    # to the appropriate type if configured.
    player1_msg1 = Player(
        id=1,
        name="Player1",
        created_at="2023-01-01T00:00:00",
        updated_at=dt1,
        possible_ban=0,
        confirmed_ban=0,
        confirmed_player=1,
        label_id=1,
        label_jagex=1,
    )
    player1_msg2 = Player(
        id=1,
        name="Player1",
        created_at="2023-01-01T00:00:00",
        updated_at=dt2,
        possible_ban=0,
        confirmed_ban=0,
        confirmed_player=1,
        label_id=1,
        label_jagex=1,
    )
    player1_msg3 = Player(
        id=1,
        name="Player1",
        created_at="2023-01-01T00:00:00",
        updated_at=dt3,
        possible_ban=0,
        confirmed_ban=0,
        confirmed_player=1,
        label_id=1,
        label_jagex=1,
    )
    player1_msg4 = Player(
        id=1,
        name="Player1",
        created_at="2023-01-01T00:00:00",
        updated_at=dt4,
        possible_ban=0,
        confirmed_ban=0,
        confirmed_player=1,
        label_id=1,
        label_jagex=1,
    )

    # For Player 2, we build three messages.
    player2_msgA = Player(
        id=2,
        name="Player2",
        created_at="2023-02-01T00:00:00",
        updated_at=dt5,
        possible_ban=0,
        confirmed_ban=0,
        confirmed_player=1,
        label_id=2,
        label_jagex=2,
    )
    player2_msgB = Player(
        id=2,
        name="Player2",
        created_at="2023-02-01T00:00:00",
        updated_at=dt6,
        possible_ban=0,
        confirmed_ban=0,
        confirmed_player=1,
        label_id=2,
        label_jagex=2,
    )
    player2_msgC = Player(
        id=2,
        name="Player2",
        created_at="2023-02-01T00:00:00",
        updated_at=dt7,
        possible_ban=0,
        confirmed_ban=0,
        confirmed_player=1,
        label_id=2,
        label_jagex=2,
    )

    # For Player 3, only one message.
    player3 = Player(
        id=3,
        name="Player3",
        created_at="2023-03-01T00:00:00",
        updated_at=dt8,
        possible_ban=0,
        confirmed_ban=0,
        confirmed_player=1,
        label_id=3,
        label_jagex=3,
    )

    # Create hiscore data for the messages.
    hiscore1 = ScraperHiscoreData(
        skills={"attack": 50},
        activities={"quest": 10},
    )
    hiscore2 = ScraperHiscoreData(
        skills={"attack": 60},
        activities={"quest": 15},
    )
    hiscore3 = ScraperHiscoreData(
        skills={"attack": 70},
        activities={"quest": 20},
    )
    hiscore_p2 = ScraperHiscoreData(
        skills={"defence": 80},
        activities={"mining": 30},
    )
    hiscore_p2_old = ScraperHiscoreData(
        skills={"defence": 75},
        activities={"mining": 25},
    )

    # Build one batch (a list of ScraperData) in an order that covers all flows.
    batch = [
        # --- Player 1 messages ---
        # Message 1: New player, hiscore provided (dt1)
        ScraperData(
            metadata=dummy_metadata,
            player_data=player1_msg1,
            hiscore_data=hiscore1,
        ),
        # Message 2: Same player, updated_at increased (dt2), no hiscore (should update player only)
        ScraperData(
            metadata=dummy_metadata,
            player_data=player1_msg2,
            hiscore_data=None,
        ),
        # Message 3: Same player, hiscore provided with an earlier timestamp than dt2 (dt3 < dt2)
        #   → hiscore update: since dt3 > dt1 (from Message 1) and same week, should replace Message 1’s hiscore.
        ScraperData(
            metadata=dummy_metadata,
            player_data=player1_msg3,
            hiscore_data=hiscore2,
        ),
        # Message 4: Same player, hiscore provided with a new week (dt4)
        #   → both player and hiscore should update.
        ScraperData(
            metadata=dummy_metadata,
            player_data=player1_msg4,
            hiscore_data=hiscore3,
        ),
        # --- Player 2 messages ---
        # Message A: New player with hiscore provided (dt5)
        ScraperData(
            metadata=dummy_metadata,
            player_data=player2_msgA,
            hiscore_data=hiscore_p2,
        ),
        # Message B: Same player, hiscore provided with an older timestamp (dt6 < dt5) → should be ignored for hiscore.
        ScraperData(
            metadata=dummy_metadata,
            player_data=player2_msgB,
            hiscore_data=hiscore_p2_old,
        ),
        # Message C: Same player, updated_at increased (dt7), no hiscore → updates player only.
        ScraperData(
            metadata=dummy_metadata,
            player_data=player2_msgC,
            hiscore_data=None,
        ),
        # --- Player 3 message ---
        # Only one message with no hiscore data.
        ScraperData(
            metadata=dummy_metadata,
            player_data=player3,
            hiscore_data=None,
        ),
    ]

    # Run the extraction.
    players, hiscores = extract_data_from_batch(batch)

    # -- Verify Players --
    # We expect players for IDs 1, 2, and 3.
    assert len(players) == 3
    player_ids = sorted([p.id for p in players])
    assert player_ids == [1, 2, 3]

    # For Player 1, the final player should come from Message 4 (dt4)
    player1_final = next(p for p in players if p.id == 1)
    assert player1_final.updated_at == dt4

    # For Player 2, the final player should come from Message C (dt7)
    player2_final = next(p for p in players if p.id == 2)
    assert player2_final.updated_at == dt7

    # For Player 3, the only message is used.
    player3_final = next(p for p in players if p.id == 3)
    assert player3_final.updated_at == dt8

    # -- Verify Hiscores --
    # The hiscores are stored in a dictionary keyed by player id.
    # After flattening, we expect:
    #   - Player 1: final hiscore from Message 4 (dt4) — it replaced earlier entries.
    #   - Player 2: hiscore from Message A (dt5) because Message B (dt6) is older.
    #   - Player 3: no hiscore because hiscore_data was None.
    hs_player1 = [hs for hs in hiscores if hs.player_id == 1]
    hs_player2 = [hs for hs in hiscores if hs.player_id == 2]
    hs_player3 = [hs for hs in hiscores if hs.player_id == 3]

    assert len(hs_player1) == 1
    # Final hiscore for Player 1 should have scrape_ts equal to dt4.
    assert hs_player1[0].scrape_ts == dt4

    assert len(hs_player2) == 1
    # Final hiscore for Player 2 should have scrape_ts equal to dt5.
    assert hs_player2[0].scrape_ts == dt5

    assert len(hs_player3) == 0
