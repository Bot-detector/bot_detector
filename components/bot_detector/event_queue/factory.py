# Backend adapters
from typing import Any, Literal, Type, TypeVar

from bot_detector.event_queue.core import (
    Queue,
    QueueConsumer,
    QueueProducer,
)
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class InvalidConfig(Exception): ...


class QueueFactory:
    @staticmethod
    def create_queue(
        model: Type[T],
        queue_type: Literal["queue", "producer", "consumer"],
        backend_type: Literal["memory", "kafka"],
        config: Any,
    ) -> Queue[T] | QueueProducer[T] | QueueConsumer[T] | Exception:
        # Backend selection
        adapter = None
        if backend_type == "memory":
            from bot_detector.event_queue.adapters.memory import (
                InMemoryAdapter,
                InMemoryConfig,
                InMemoryConsumerAdapter,
                InMemoryProducerAdapter,
            )

            if not isinstance(config, InMemoryConfig):
                return InvalidConfig(
                    f"Expected config of type: InMemoryConfig but received: {type(config)}"
                )

            adapter = {
                "producer": InMemoryProducerAdapter[model](cls=model, config=config),
                "consumer": InMemoryConsumerAdapter[model](cls=model, config=config),
                "queue": InMemoryAdapter[model](cls=model, config=config),
            }[queue_type]
        elif backend_type == "kafka":
            from bot_detector.event_queue.adapters.kafka import (
                AIOKafkaAdapter,
                AIOKafkaConsumerAdapter,
                AIOKafkaProducerAdapter,
                KafkaConfig,
            )

            if not isinstance(config, KafkaConfig):
                return InvalidConfig(
                    f"Expected config of type: KafkaConfig but received: {type(config)}"
                )

            adapter = {
                "producer": AIOKafkaProducerAdapter[model](cls=model, config=config),
                "consumer": AIOKafkaConsumerAdapter[model](cls=model, config=config),
                "queue": AIOKafkaAdapter[model](cls=model, config=config),
            }[queue_type]

        if adapter is None:
            raise ValueError(f"Unknown backend: {backend_type=}, {queue_type=}")

        # Queue type selection
        queue = {
            "producer": QueueProducer[model](adapter),
            "consumer": QueueConsumer[model](adapter),
            "queue": Queue[model](adapter),
        }[queue_type]
        return queue
