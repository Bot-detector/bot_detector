# Backend adapters
from typing import Any, Literal, Type, TypeVar

from bot_detector.event_queue.core import (
    Queue,
    QueueConsumer,
    QueueProducer,
)
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class QueueFactory:
    @staticmethod
    def create_queue(
        model: Type[T],
        queue_type: Literal["queue", "producer", "consumer"],
        backend_type: Literal["memory", "kafka"],
        config: dict | Any,
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

            if isinstance(config, dict):
                _config = InMemoryConfig.model_validate(config)
            elif isinstance(config, InMemoryConfig):
                _config = config

            adapter = {
                "producer": InMemoryProducerAdapter[model](model, config=_config),
                "consumer": InMemoryConsumerAdapter[model](model, config=_config),
                "queue": InMemoryAdapter[model](model, config=_config),
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
