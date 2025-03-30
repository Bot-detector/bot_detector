import datetime
import logging
from unittest.mock import AsyncMock

import pytest
from bot_detector.database.structs import PlayerStruct
from bot_detector.schema import Player
from bot_detector.scrape_task_producer.core import produce_players

### Testing Philosophy: define expected behavior


## Basic Functionality Tests
@pytest.mark.asyncio
async def test_produce_players_valid_list(caplog):
    """
    Test a valid player calls produce_players once.
    """
    mock_producer = AsyncMock()
    player = PlayerStruct(
        id=1,
        name="ValidPlayer",
        normalized_name="validplayer",
        created_at=datetime.datetime(2025, 1, 1, 12, 0, 0),
        updated_at=datetime.datetime(2025, 1, 2, 12, 0, 0),
        possible_ban=False,
        confirmed_ban=False,
        confirmed_player=True,
        ironman=False,
        hardcore_ironman=False,
        ultimate_ironman=False,
        label_id=1,
        label_jagex=1,
    )
    await produce_players(players=[player], player_producer=mock_producer)
    mock_producer.produce_one.assert_called_once_with(player=player)


## Edge Cases


@pytest.mark.asyncio
async def test_produce_players_empty_list(caplog):
    """
    Test that produce_players handles an empty list of players gracefully.
    """
    mock_producer = AsyncMock()
    await produce_players(players=[], player_producer=mock_producer)
    mock_producer.produce_one.assert_not_called()


## Invalid input tests


@pytest.mark.asyncio
async def test_produce_players_invalid_player_type(caplog):
    """
    Test that produce_players skips invalid players.
    """
    mock_producer = AsyncMock()
    invalid_player = {"id": 1, "name": "InvalidPlayer"}  # Not a PlayerStruct
    await produce_players(players=[invalid_player], player_producer=mock_producer)
    mock_producer.produce_one.assert_not_called()


@pytest.mark.asyncio
async def test_produce_players_invalid_object(caplog):
    """
    Test that produce_players skips invalid players without raising an exception
    and does not call produce_one for invalid players.
    """
    mock_producer = AsyncMock()

    # Pass an invalid player (not a PlayerStruct)
    invalid_player = {"id": 1, "name": "InvalidPlayer"}  # Not a PlayerStruct

    # Call produce_players with the invalid player
    await produce_players(players=[invalid_player], player_producer=mock_producer)

    # Assert that no exception is raised and no calls are made to produce_one
    mock_producer.produce_one.assert_not_called()


## Resilience Tests


# Should this raise an error or handle gracefully? @extreme
@pytest.mark.asyncio
async def test_produce_players_producer_raises_error():
    """
    Test that produce_players raises an exception if the producer raises an error.
    """
    mock_producer = AsyncMock()
    mock_producer.produce_one.side_effect = Exception("Kafka error")

    player = PlayerStruct(
        id=1,
        name="BadProducer",
        normalized_name="badproducer",
        created_at=datetime.datetime(2025, 1, 1, 12, 0, 0),
        updated_at=datetime.datetime(2025, 1, 2, 12, 0, 0),
        possible_ban=False,
        confirmed_ban=False,
        confirmed_player=True,
        ironman=False,
        hardcore_ironman=False,
        ultimate_ironman=False,
        label_id=1,
        label_jagex=1,
    )

    with pytest.raises(Exception, match="Kafka error"):
        await produce_players(players=[player], player_producer=mock_producer)


@pytest.mark.asyncio
async def test_produce_players_resilience(caplog):
    """
    This test sends one player record and uses a mock producer that raises an exception.
    It verifies that when produce_one fails, the exception is propagated.
    """
    # Create a sample player record
    test_player = Player(
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

    players = [test_player]

    # Create a mock producer where produce_one raises an exception
    mock_producer = AsyncMock()
    mock_producer.produce_one.side_effect = Exception(
        "Simulated failure for resilience test"
    )

    # Assert the exception is raised
    with pytest.raises(Exception, match="Simulated failure for resilience test"):
        await produce_players(players, mock_producer)

    # Assert the log message
    assert "Putting 1 players in queue" in caplog.text


@pytest.mark.asyncio
async def test_produce_players_partial_failure(caplog):
    """
    Test that partial failure during player production raises an exception and logs appropriately.
    """
    caplog.set_level(logging.INFO)

    mock_producer = AsyncMock()
    mock_producer.produce_one.side_effect = [None, Exception("oops")]

    player1 = PlayerStruct(
        id=1,
        name="Player1",
        normalized_name="player1",
        created_at=datetime.datetime(2025, 1, 1, 12, 0, 0),
        updated_at=datetime.datetime(2025, 1, 2, 12, 0, 0),
        possible_ban=False,
        confirmed_ban=False,
        confirmed_player=True,
        ironman=True,
        hardcore_ironman=False,
        ultimate_ironman=False,
        label_id=10,
        label_jagex=20,
    )
    player2 = PlayerStruct(
        id=2,
        name="Player2",
        normalized_name="player2",
        created_at=datetime.datetime(2025, 1, 3, 12, 0, 0),
        updated_at=datetime.datetime(2025, 1, 4, 12, 0, 0),
        possible_ban=True,
        confirmed_ban=False,
        confirmed_player=False,
        ironman=False,
        hardcore_ironman=False,
        ultimate_ironman=True,
        label_id=11,
        label_jagex=21,
    )

    with pytest.raises(Exception, match="oops"):
        await produce_players(players=[player1, player2], player_producer=mock_producer)

    assert "Putting 2 players in queue" in caplog.text


## Performance/Stress Tests
@pytest.mark.asyncio
async def test_produce_players_large_input(caplog):
    """
    Test that produce_players handles a large number of players efficiently.
    """
    mock_producer = AsyncMock()
    players = [
        PlayerStruct(
            id=i,
            name=f"Player{i}",
            normalized_name=f"player{i}",
            created_at=datetime.datetime(2025, 1, 1, 12, 0, 0),
            updated_at=datetime.datetime(2025, 1, 2, 12, 0, 0),
            possible_ban=False,
            confirmed_ban=False,
            confirmed_player=True,
            ironman=False,
            hardcore_ironman=False,
            ultimate_ironman=False,
            label_id=1,
            label_jagex=1,
        )
        for i in range(1000)
    ]
    await produce_players(players=players, player_producer=mock_producer)
    assert "Putting 1000 players in queue" in caplog.text
    assert mock_producer.produce_one.call_count == 1000


## Logging and Monitoring Tests
@pytest.mark.asyncio
async def test_produce_players_logging(caplog):
    """
    Test that produce_players logs appropriate messages for key events.
    """
    mock_producer = AsyncMock()
    player = PlayerStruct(
        id=1,
        name="Player1",
        normalized_name="player1",
        created_at=datetime.datetime(2025, 1, 1, 12, 0, 0),
        updated_at=datetime.datetime(2025, 1, 2, 12, 0, 0),
        possible_ban=False,
        confirmed_ban=False,
        confirmed_player=True,
        ironman=False,
        hardcore_ironman=False,
        ultimate_ironman=False,
        label_id=1,
        label_jagex=1,
    )
    await produce_players(players=[player], player_producer=mock_producer)
    assert "Putting 1 players in queue" in caplog.text
