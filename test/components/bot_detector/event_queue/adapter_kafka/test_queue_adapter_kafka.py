from unittest.mock import AsyncMock

import pytest
from bot_detector.event_queue.adapters.kafka import (
    AIOKafkaAdapter,
    KafkaConfig,
    KafkaConsumerConfig,
    KafkaProducerConfig,
)
from pydantic import BaseModel


class PlayerScraped(BaseModel):
    id: int
    username: str
    score: int


@pytest.mark.asyncio
async def test_queue_adapter_wiring():
    config = KafkaConfig(
        topic="players",
        bootstrap_servers="localhost:9092",
        consumer=True,
        producer=True,
        consumer_config=KafkaConsumerConfig(group_id="group"),
        producer_config=KafkaProducerConfig(partition_key_fn=lambda: "1"),
    )
    adapter = AIOKafkaAdapter(PlayerScraped, config)
    adapter.producer.start = AsyncMock()
    adapter.consumer.start = AsyncMock()
    adapter.producer.stop = AsyncMock()
    adapter.consumer.stop = AsyncMock()
    adapter.producer.put = AsyncMock()
    adapter.consumer.get_one = AsyncMock(return_value="one")
    adapter.consumer.get_many = AsyncMock(return_value=["many"])
    adapter.consumer.commit = AsyncMock()

    await adapter.start()
    await adapter.put([PlayerScraped(id=1, username="Alice", score=100)])
    one = await adapter.get_one()
    many = await adapter.get_many(2)
    await adapter.commit()
    await adapter.stop()

    adapter.producer.start.assert_awaited_once()
    adapter.consumer.start.assert_awaited_once()
    adapter.producer.put.assert_awaited_once()
    adapter.consumer.get_one.assert_awaited_once()
    adapter.consumer.get_many.assert_awaited_once()
    adapter.consumer.commit.assert_awaited_once()
    adapter.consumer.stop.assert_awaited_once()
    adapter.producer.stop.assert_awaited_once()
    assert one == "one"
    assert many == ["many"]
