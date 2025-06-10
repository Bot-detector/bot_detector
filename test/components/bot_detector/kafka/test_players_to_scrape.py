from unittest.mock import AsyncMock

import pytest
from aiokafka.structs import TopicPartition
from bot_detector.kafka.repositories.players_to_scrape import (
    RepoPlayersToScrapeConsumer,
)


@pytest.fixture
def fake_consumer():
    """Fixture to create a fake Kafka consumer with default behavior."""
    mock_consumer = AsyncMock()
    mock_consumer.partitions_for_topic = lambda topic: {0}
    tp = TopicPartition("players.to_scrape", 0)
    # These will be overridden in each test if needed
    mock_consumer.committed = AsyncMock(return_value=None)
    mock_consumer.end_offsets = AsyncMock(return_value={tp: 10})
    return mock_consumer


@pytest.mark.asyncio
async def test_get_lag_handles_none_committed(fake_consumer):
    # Default committed is None (set in the fixture)
    consumer = RepoPlayersToScrapeConsumer("test-group", ["localhost:9092"])
    consumer.consumer = fake_consumer

    lag = await consumer.get_lag()
    assert lag == 10  # If committed is None, lag should be full length


@pytest.mark.asyncio
async def test_get_lag_handles_committed_zero(fake_consumer):
    fake_consumer.committed = AsyncMock(return_value=0)  # Override for this test
    consumer = RepoPlayersToScrapeConsumer("test-group", ["localhost:9092"])
    consumer.consumer = fake_consumer

    lag = await consumer.get_lag()
    assert lag == 10  # 10-0
