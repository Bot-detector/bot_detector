from unittest.mock import AsyncMock, patch

import pytest
from aiokafka.errors import KafkaTimeoutError
from bot_detector.event_queue.adapters.kafka import (
    AIOKafkaConsumerAdapter,
    AIOKafkaProducerAdapter,
    KafkaConfig,
    KafkaConsumerConfig,
    KafkaProducerConfig,
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
        producer_config=KafkaProducerConfig(partition_key_fn=lambda: 1),
    )

    adapter = AIOKafkaProducerAdapter(PlayerScraped, config)

    # Patch AIOKafkaProducer in the adapter to prevent real network calls
    with patch(
        "bot_detector.event_queue.adapters.kafka.adapter.AIOKafkaProducer"
    ) as MockProducer:
        mock_producer = MockProducer.return_value
        mock_producer.start = AsyncMock()
        mock_producer.send = AsyncMock(side_effect=[KafkaTimeoutError("fail"), None])
        mock_producer.stop = AsyncMock()

        await adapter.start()  # now uses the mock, no network call
        await adapter.put([PlayerScraped(username="Alice", score=100)])
        assert mock_producer.send.call_count == 2


@pytest.mark.asyncio
async def test_consumer_get_one_validation():
    config = KafkaConfig(
        topic="",
        bootstrap_servers="",
        consumer=True,
        producer=False,
        consumer_config=KafkaConsumerConfig(group_id=""),
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
