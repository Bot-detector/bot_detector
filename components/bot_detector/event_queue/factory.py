from typing import Any, Literal, TypeVar

from bot_detector.event_queue.adapters.kafka import KafkaLagProbe
from bot_detector.event_queue.adapters.memory import MemoryLagProbe
from bot_detector.event_queue.core import (
    Queue,
    QueueBackendConsumerProtocol,
    QueueBackendProducerProtocol,
    QueueBackendProtocol,
    QueueConsumer,
    QueueProducer,
)
from bot_detector.event_queue.lag_probe import LagProbeProtocol
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class InvalidConfig(Exception): ...


def create_adapter_memory(
    model: type[T],
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
    model: type[T],
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


def create_lag_probe(
    backend_type: Literal["memory", "kafka"],
    bootstrap_servers: str | None = None,
) -> LagProbeProtocol | Exception:
    match backend_type:
        case "memory":
            return MemoryLagProbe()
        case "kafka":
            if bootstrap_servers is None:
                return ValueError("bootstrap_servers is required for kafka lag probe")
            return KafkaLagProbe(bootstrap_servers=bootstrap_servers)
        case _:
            return ValueError(f"Unknown backend_type: {backend_type}")


class QueueFactory:
    @staticmethod
    def create_queue(
        model: type[T],
        queue_type: Literal["queue", "producer", "consumer"],
        backend_type: Literal["memory", "kafka"],
        config: Any,
    ) -> Queue[T] | QueueProducer[T] | QueueConsumer[T] | Exception:
        match backend_type:
            case "memory":
                adapter = create_adapter_memory(model, config, queue_type)
            case "kafka":
                adapter = create_adapter_kafka(model, config, queue_type)
            case _:
                return ValueError(f"Unknown backend_type: {backend_type}")

        match queue_type:
            case "queue" if isinstance(adapter, QueueBackendProtocol):
                queue = Queue[model](adapter)
            case "producer" if isinstance(adapter, QueueBackendProducerProtocol):
                queue = QueueProducer[model](adapter)
            case "consumer" if isinstance(adapter, QueueBackendConsumerProtocol):
                queue = QueueConsumer[model](adapter)
            case _:
                return ValueError(f"Unknown queue_type: {queue_type}")
        return queue
