import datetime
from unittest.mock import AsyncMock, patch

import pytest
from bot_detector.database.structs import PlayerStruct
from bot_detector.kafka.repositories.players_to_scrape import (
    RepoPlayersToScrapeProducer,
)


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
        assert isinstance(kwargs["value"], dict) or isinstance(kwargs["value"], bytes)

        await producer.stop()
        mock_instance.stop.assert_called_once()


@pytest.mark.asyncio
async def test_produce_one_invalid():
    mock_producer = AsyncMock()
    producer = RepoPlayersToScrapeProducer(bootstrap_servers=["localhost:9092"])
    producer.producer = mock_producer

    invalid_player = {"id": 1, "name": "Invalid Player"}

    with pytest.raises(Exception):
        await producer.produce_one(invalid_player)


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
