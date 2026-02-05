from typing import Any, Literal, Type, TypeVar

from bot_detector.event_queue.core import (
    Queue,
    QueueBackendConsumerProtocol,
    QueueBackendProducerProtocol,
    QueueBackendProtocol,
    QueueConsumer,
    QueueProducer,
)
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class InvalidConfig(Exception): ...


def create_adapter_memory(
    model: Type[T],
    config: Any,
    queue_type: Literal["queue", "producer", "consumer"],
) -> (
    QueueBackendProtocol[T]
    | QueueBackendProducerProtocol[T]
    | QueueBackendConsumerProtocol[T]
):
    from bot_detector.event_queue.adapters.memory import (
        InMemoryAdapter,
        InMemoryConfig,
        InMemoryConsumerAdapter,
        InMemoryProducerAdapter,
    )

    if not isinstance(config, InMemoryConfig):
        raise InvalidConfig(f"Expected InMemoryConfig but got {type(config)}")

    if queue_type == "queue":
        return InMemoryAdapter[model](cls=model, config=config)
    elif queue_type == "producer":
        return InMemoryProducerAdapter[model](cls=model, config=config)
    else:  # consumer
        return InMemoryConsumerAdapter[model](cls=model, config=config)


def create_adapter_kafka(
    model: Type[T],
    config: Any,
    queue_type: Literal["queue", "producer", "consumer"],
) -> (
    QueueBackendProtocol[T]
    | QueueBackendProducerProtocol[T]
    | QueueBackendConsumerProtocol[T]
):
    from bot_detector.event_queue.adapters.kafka import (
        AIOKafkaAdapter,
        AIOKafkaConsumerAdapter,
        AIOKafkaProducerAdapter,
        KafkaConfig,
    )

    if not isinstance(config, KafkaConfig):
        raise InvalidConfig(f"Expected KafkaConfig but got {type(config)}")

    if queue_type == "queue":
        return AIOKafkaAdapter[model](cls=model, config=config)
    elif queue_type == "producer":
        return AIOKafkaProducerAdapter[model](cls=model, config=config)
    else:  # consumer
        return AIOKafkaConsumerAdapter[model](cls=model, config=config)


class QueueFactory:
    @staticmethod
    def create_queue(
        model: Type[T],
        queue_type: Literal["queue", "producer", "consumer"],
        backend_type: Literal["memory", "kafka"],
        config: Any,
    ) -> Queue[T] | QueueProducer[T] | QueueConsumer[T] | Exception:
        if backend_type == "memory":
            adapter = create_adapter_memory(model, config, queue_type)
        elif backend_type == "kafka":
            adapter = create_adapter_kafka(model, config, queue_type)
        else:
            return ValueError(f"Unknown backend_type: {backend_type}")

        if queue_type == "queue" and isinstance(adapter, QueueBackendProtocol):
            queue = Queue[model](adapter)
        elif queue_type == "producer" and isinstance(
            adapter, QueueBackendProducerProtocol
        ):
            queue = QueueProducer[model](adapter)
        elif queue_type == "consumer" and isinstance(
            adapter, QueueBackendConsumerProtocol
        ):
            queue = QueueConsumer[model](adapter)
        else:
            queue = ValueError(f"Unknown queue_type: {backend_type}")
        return queue
