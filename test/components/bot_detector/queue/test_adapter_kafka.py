from unittest.mock import AsyncMock

import pytest
from bot_detector.queue.adapters.kafka import (
    AIOKafkaConsumerAdapter,
    AIOKafkaProducerAdapter,
    KafkaConfig,
)
from pydantic import BaseModel


class PlayerScraped(BaseModel):
    username: str
    score: int


@pytest.mark.asyncio
async def test_producer_put_retries():
    config = KafkaConfig(
        topic="",
        bootstrap_servers="",
        consumer=False,
        producer=True,
        consumer_config=None,
        producer_config=None,
    )
    adapter = AIOKafkaProducerAdapter(PlayerScraped, config)

    # Patch producer.send to fail the first time, then succeed
    mock_send = AsyncMock(side_effect=[Exception("fail"), None])
    adapter.producer = AsyncMock()
    adapter.producer.send = mock_send

    await adapter.start()
    await adapter.put([PlayerScraped(username="Alice", score=100)])
    assert mock_send.call_count == 2


@pytest.mark.asyncio
async def test_consumer_get_one_validation():
    config = KafkaConfig(
        topic="",
        bootstrap_servers="",
        consumer=False,
        producer=True,
        consumer_config=None,
        producer_config=None,
    )
    adapter = AIOKafkaConsumerAdapter(PlayerScraped, config)

    fake_record = AsyncMock()
    fake_record.value = {"username": "Alice", "score": 100}

    adapter.consumer = AsyncMock()
    adapter.consumer.getone = AsyncMock(return_value=fake_record)

    result = await adapter.get_one()
    assert isinstance(result, PlayerScraped)
    assert result.username == "Alice"
