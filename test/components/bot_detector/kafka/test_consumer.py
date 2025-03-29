import datetime
from unittest.mock import AsyncMock, patch

import pytest
from bot_detector.database.structs import PlayerStruct
from bot_detector.kafka.repositories.players_to_scrape import (
    RepoPlayersToScrapeConsumer,
)


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
