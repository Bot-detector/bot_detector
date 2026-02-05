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


def test_queue_factory_creates_kafka_queue():
    config = KafkaConfig(
        topic="players",
        bootstrap_servers="localhost:9092",
        consumer=True,
        producer=True,
        consumer_config=KafkaConsumerConfig(group_id="group"),
        producer_config=KafkaProducerConfig(partition_key_fn=lambda: "1"),
    )

    queue = QueueFactory.create_queue(
        PlayerScraped,
        queue_type="queue",
        backend_type="kafka",
        config=config,
    )

    assert isinstance(queue, Queue)
    assert isinstance(queue._backend, AIOKafkaAdapter)
