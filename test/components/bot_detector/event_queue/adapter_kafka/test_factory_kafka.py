from unittest.mock import AsyncMock

import pytest
from bot_detector.event_queue.adapters.kafka import (
    AIOKafkaAdapter,
    KafkaConfig,
    KafkaConsumerConfig,
    KafkaProducerConfig,
)
from bot_detector.event_queue.core.event_queue import Queue
from bot_detector.event_queue.factory import QueueFactory
from pydantic import BaseModel


class PlayerScraped(BaseModel):
    id: int
    username: str
    score: int


@pytest.mark.asyncio
async def test_queue_factory_creates_kafka_queue():
    config = KafkaConfig(
        topic="players",
        bootstrap_servers="localhost:9092",
        consumer=True,
        producer=True,
        consumer_config=KafkaConsumerConfig(group_id="group"),
        producer_config=KafkaProducerConfig(partition_key_fn=lambda _: "1"),
    )

    queue = QueueFactory.create_queue(
        PlayerScraped,
        queue_type="queue",
        backend_type="kafka",
        config=config,
    )

    assert isinstance(queue, Queue)
    assert isinstance(queue._backend, AIOKafkaAdapter)

    queue._backend.start = AsyncMock()
    queue._backend.stop = AsyncMock()
    queue._backend.put = AsyncMock()
    queue._backend.get_one = AsyncMock(return_value="one")
    queue._backend.get_many = AsyncMock(return_value=["many"])

    await queue.start()
    await queue.put([PlayerScraped(id=1, username="Alice", score=100)])
    one = await queue.get_one()
    many = await queue.get_many(2)
    await queue.stop()

    queue._backend.start.assert_awaited_once()
    queue._backend.put.assert_awaited_once()
    queue._backend.get_one.assert_awaited_once()
    queue._backend.get_many.assert_awaited_once_with(2)
    queue._backend.stop.assert_awaited_once()
    assert one == "one"
    assert many == ["many"]
