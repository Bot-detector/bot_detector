import asyncio
import datetime
import logging
from unittest.mock import AsyncMock, patch

import pytest
from bot_detector.database.structs import PlayerStruct
from bot_detector.kafka.repositories.players_to_scrape import (
    RepoPlayersToScrapeConsumer,
    RepoPlayersToScrapeProducer,
)
from bot_detector.schema import Player
from bot_detector.scrape_task_producer.core import (
    determine_fetch_params,
    # fetch_players,
    produce_players,
    # put_players_in_queue,
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


# --- produce_players Functionality ---
@pytest.mark.asyncio
async def test_produce_one_sends_correct_value():
    player = PlayerStruct(
        id=1,
        name="TestPlayer",
        normalized_name="testplayer",
        created_at=datetime.datetime.utcnow(),
        updated_at=datetime.datetime.utcnow(),
        possible_ban=False,
        confirmed_ban=False,
        confirmed_player=True,
        ironman=False,
        hardcore_ironman=False,
        ultimate_ironman=False,
        label_id=123,
        label_jagex=456,
    )

    with patch(
        "bot_detector.kafka.repositories.players_to_scrape.AIOKafkaProducer"
    ) as MockProducer:
        mock_instance = AsyncMock()
        MockProducer.return_value = mock_instance

        producer = RepoPlayersToScrapeProducer(bootstrap_servers=["mockserver:9092"])
        await producer.start()

        await producer.produce_one(player)

        mock_instance.send.assert_called_once()
        args, kwargs = mock_instance.send.call_args
        assert kwargs["topic"] == "players.to_scrape"
        assert isinstance(kwargs["value"], dict) or isinstance(
            kwargs["value"], bytes
        )  # depending on serializer

        await producer.stop()
        mock_instance.stop.assert_called_once()


@pytest.mark.asyncio
async def test_produce_players_resilience(caplog):
    """
    This test sends one player record and uses a mock producer that raises an exception.
    It verifies that when produce_one fails, the exception is propagated.
    """
    # Set the logging level to INFO
    with caplog.at_level(logging.INFO, logger="bot_detector.scrape_task_producer.core"):
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


# Test that partial failure during player production raises an exception and logs appropriately.
@pytest.mark.asyncio
async def test_produce_players_partial_failure(caplog):
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


# Test that producing a non-PlayerStruct object raises an exception.
@pytest.mark.asyncio
async def test_produce_players_invalid_object():
    mock_producer = AsyncMock()
    # Configure the mock to raise when called with invalid player
    mock_producer.produce_one.side_effect = Exception("invalid player")

    with pytest.raises(Exception, match="invalid player"):
        await produce_players([{"id": 1}], mock_producer)


# --- RepoPlayersToScrapeProducer Specific Tests ---
@pytest.mark.asyncio
async def test_produce_one_invalid():
    """
    Test that produce_one raises an exception when the player is not a PlayerStruct.
    """
    # Mock the producer
    mock_producer = AsyncMock()
    repo_producer = RepoPlayersToScrapeProducer(bootstrap_servers=["localhost:9092"])
    repo_producer.producer = mock_producer

    # Pass an invalid player object
    invalid_player = {"id": 1, "name": "Invalid Player"}

    # Assert that an exception is raised
    with pytest.raises(Exception, match=""):
        await repo_producer.produce_one(invalid_player)


@pytest.mark.asyncio
async def test_producer_start_and_stop():
    with patch(
        "bot_detector.kafka.repositories.players_to_scrape.AIOKafkaProducer"
    ) as MockProducer:
        mock_instance = AsyncMock()
        MockProducer.return_value = mock_instance

        producer = RepoPlayersToScrapeProducer(bootstrap_servers=["mockserver:9092"])
        await producer.start()
        mock_instance.start.assert_called_once()

        await producer.stop()
        mock_instance.stop.assert_called_once()


# --- RepoPlayersToScrapeConsumer Specific Tests ---
@pytest.mark.asyncio
async def test_consume_one_returns_player():
    sample_data = {
        "id": 42,
        "name": "TestPlayer",
        "normalized_name": "testplayer",
        "created_at": datetime.datetime.utcnow(),
        "updated_at": datetime.datetime.utcnow(),
        "possible_ban": False,
        "confirmed_ban": False,
        "confirmed_player": True,
        "ironman": False,
        "hardcore_ironman": False,
        "ultimate_ironman": False,
        "label_id": 12,
        "label_jagex": 34,
    }

    mock_msg = AsyncMock()
    mock_msg.value = sample_data

    with patch(
        "bot_detector.kafka.repositories.players_to_scrape.AIOKafkaConsumer"
    ) as MockConsumer:
        mock_instance = AsyncMock()
        mock_instance.getone.return_value = mock_msg
        MockConsumer.return_value = mock_instance

        consumer = RepoPlayersToScrapeConsumer(group_id="test-group")
        await consumer.start()
        player = await consumer.consume_one()

        assert isinstance(player, PlayerStruct)
        assert player.name == "TestPlayer"
        await consumer.stop()


@pytest.mark.asyncio
async def test_consume_one_invalid_payload():
    mock_msg = AsyncMock()
    mock_msg.value = {"id": 42, "name": "Missing fields!"}

    with patch(
        "bot_detector.kafka.repositories.players_to_scrape.AIOKafkaConsumer"
    ) as MockConsumer:
        mock_instance = AsyncMock()
        mock_instance.getone.return_value = mock_msg
        MockConsumer.return_value = mock_instance

        consumer = RepoPlayersToScrapeConsumer(group_id="test-group")
        await consumer.start()
        with pytest.raises(TypeError):
            await consumer.consume_one()
        await consumer.stop()


@pytest.mark.asyncio
async def test_produce_one_serialization_failure():
    player = PlayerStruct(
        id=1,
        name="TestPlayer",
        normalized_name="testplayer",
        created_at=datetime.datetime.utcnow(),
        updated_at=datetime.datetime.utcnow(),
        possible_ban=False,
        confirmed_ban=False,
        confirmed_player=True,
        ironman=False,
        hardcore_ironman=False,
        ultimate_ironman=False,
        label_id=123,
        label_jagex=456,
    )
    # Inject a non-serializable object
    player.created_at = object()

    with patch(
        "bot_detector.kafka.repositories.players_to_scrape.AIOKafkaProducer"
    ) as MockProducer:
        mock_instance = AsyncMock()
        mock_instance.send.side_effect = Exception("serialization failed")
        MockProducer.return_value = mock_instance

        producer = RepoPlayersToScrapeProducer(bootstrap_servers=["mockserver:9092"])
        await producer.start()

        with pytest.raises(Exception, match="serialization failed"):
            await producer.produce_one(player)

        await producer.stop()
