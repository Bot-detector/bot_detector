from unittest.mock import AsyncMock

import pytest
from aiokafka.structs import TopicPartition
from bot_detector.kafka.repositories.players_to_scrape import (
    RepoPlayersToScrapeConsumer,
)


@pytest.mark.asyncio
async def test_get_lag_handles_none_committed(monkeypatch):
    # Setup a fake Kafka consumer
    fake_consumer = AsyncMock()
    fake_consumer.partitions_for_topic = AsyncMock(return_value={0})
    tp = TopicPartition("players.to_scrape", 0)
    fake_consumer.committed = AsyncMock(return_value=None)
    fake_consumer.end_offsets = AsyncMock(return_value={tp: 10})

    # Patch the real consumer with the fake
    consumer = RepoPlayersToScrapeConsumer("test-group", ["localhost:9092"])
    consumer.consumer = fake_consumer

    lag = await consumer.get_lag()
    assert lag == 10  # If committed is None, lag should be full length


@pytest.mark.asyncio
async def test_get_lag_handles_committed_zero(monkeypatch):
    fake_consumer = AsyncMock()
    fake_consumer.partitions_for_topic = AsyncMock(return_value={0})
    tp = TopicPartition("players.to_scrape", 0)
    fake_consumer.committed = AsyncMock(return_value=0)
    fake_consumer.end_offsets = AsyncMock(return_value={tp: 10})

    consumer = RepoPlayersToScrapeConsumer("test-group", ["localhost:9092"])
    consumer.consumer = fake_consumer

    lag = await consumer.get_lag()
    assert lag == 10  # 10-0
