from typing import Optional

import pytest
from bot_detector.event_queue.adapters.memory import InMemoryAdapter, InMemoryConfig
from bot_detector.event_queue.core.event_queue import (
    Queue,
    QueueConsumer,
    QueueProducer,
    _get_many_outcome,
)
from bot_detector.event_queue.factory import QueueFactory
from prometheus_client import REGISTRY
from pydantic import BaseModel


class MetricsMessage(BaseModel):
    value: int


class OtherMessage(BaseModel):
    value: int


class ExplodingProducerBackend:
    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def put(self, messages: list[MetricsMessage]) -> Optional[Exception]:
        return RuntimeError("backend down")


class ExplodingConsumerBackend:
    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def get_one(self) -> Optional[MetricsMessage] | Exception:
        return RuntimeError("backend down")

    async def get_many(self, count: int) -> list[MetricsMessage] | Exception:
        return RuntimeError("backend down")

    async def commit(self) -> Optional[Exception]:
        return None


class StaticBatchBackend:
    def __init__(self, batch: list[MetricsMessage] | Exception):
        self.batch = batch

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def get_one(self) -> Optional[MetricsMessage] | Exception:
        return None

    async def get_many(self, count: int) -> list[MetricsMessage] | Exception:
        return self.batch

    async def commit(self) -> Optional[Exception]:
        return None


def _sample(name: str, labels: dict[str, str]) -> float | None:
    return REGISTRY.get_sample_value(name, labels)


def _queue(name: str) -> Queue[MetricsMessage]:
    return Queue[MetricsMessage](
        backend=InMemoryAdapter(cls=MetricsMessage, config=InMemoryConfig(maxsize=100)),
        name=name,
    )


@pytest.mark.asyncio
async def test_put_increments_produced_counter():
    queue = _queue("metrics-produce")
    await queue.start()

    result = await queue.put([MetricsMessage(value=i) for i in range(3)])

    assert result is None
    produced = _sample(
        "event_queue_messages_produced_total", {"queue": "metrics-produce"}
    )
    assert produced == 3

    await queue.stop()


@pytest.mark.asyncio
async def test_put_error_does_not_count_produced():
    producer = QueueProducer[MetricsMessage](
        backend=ExplodingProducerBackend(), name="metrics-produce-error"
    )
    await producer.start()

    result = await producer.put([MetricsMessage(value=1)])

    assert isinstance(result, Exception)
    produced = _sample(
        "event_queue_messages_produced_total", {"queue": "metrics-produce-error"}
    )
    assert produced is None

    await producer.stop()


@pytest.mark.asyncio
async def test_get_one_counts_consumed_and_latency():
    queue = _queue("metrics-get-one")
    await queue.start()
    await queue.put([MetricsMessage(value=i) for i in range(2)])

    first = await queue.get_one()
    second = await queue.get_one()

    assert isinstance(first, MetricsMessage)
    assert isinstance(second, MetricsMessage)
    consumed = _sample(
        "event_queue_messages_consumed_total", {"queue": "metrics-get-one"}
    )
    latency_count = _sample(
        "event_queue_get_seconds_count",
        {"queue": "metrics-get-one", "op": "get_one"},
    )
    assert consumed == 2
    assert latency_count == 2

    await queue.stop()


@pytest.mark.asyncio
async def test_get_one_empty_does_not_count_consumed():
    queue = _queue("metrics-get-one-empty")
    await queue.start()

    result = await queue.get_one()

    assert result is None
    consumed = _sample(
        "event_queue_messages_consumed_total", {"queue": "metrics-get-one-empty"}
    )
    latency_count = _sample(
        "event_queue_get_seconds_count",
        {"queue": "metrics-get-one-empty", "op": "get_one"},
    )
    assert consumed is None
    assert latency_count == 1

    await queue.stop()


@pytest.mark.asyncio
async def test_get_many_counts_consumed_and_latency():
    queue = _queue("metrics-get-many")
    await queue.start()
    await queue.put([MetricsMessage(value=i) for i in range(3)])

    batch = await queue.get_many(10)

    assert len(batch) == 3
    consumed = _sample(
        "event_queue_messages_consumed_total", {"queue": "metrics-get-many"}
    )
    latency_count = _sample(
        "event_queue_get_seconds_count",
        {"queue": "metrics-get-many", "op": "get_many"},
    )
    assert consumed == 3
    assert latency_count == 1

    await queue.stop()


@pytest.mark.asyncio
async def test_consumer_error_does_not_count_consumed():
    consumer = QueueConsumer[MetricsMessage](
        backend=ExplodingConsumerBackend(), name="metrics-consume-error"
    )
    await consumer.start()

    one = await consumer.get_one()
    many = await consumer.get_many(5)

    assert isinstance(one, Exception)
    assert isinstance(many, Exception)
    consumed = _sample(
        "event_queue_messages_consumed_total", {"queue": "metrics-consume-error"}
    )
    assert consumed is None
    for op in ("get_one", "get_many"):
        latency_count = _sample(
            "event_queue_get_seconds_count",
            {"queue": "metrics-consume-error", "op": op},
        )
        assert latency_count == 1

    await consumer.stop()


@pytest.mark.asyncio
async def test_factory_labels_metrics_with_model_name():
    queue = QueueFactory.create_queue(
        model=OtherMessage,
        queue_type="queue",
        backend_type="memory",
        config=InMemoryConfig(maxsize=10),
    )
    assert not isinstance(queue, Exception)
    assert queue._name == "OtherMessage"
    await queue.start()

    await queue.put([OtherMessage(value=1)])
    await queue.get_many(5)

    produced = _sample("event_queue_messages_produced_total", {"queue": "OtherMessage"})
    consumed = _sample("event_queue_messages_consumed_total", {"queue": "OtherMessage"})
    assert produced == 1
    assert consumed == 1

    await queue.stop()


@pytest.mark.parametrize(
    "size,count,expected",
    [
        (0, 10, "empty"),
        (1, 10, "partial"),
        (9, 10, "partial"),
        (10, 10, "full"),
        (11, 10, "full"),
    ],
)
def test_get_many_outcome_classification(size, count, expected):
    assert _get_many_outcome(size=size, count=count) == expected


@pytest.mark.asyncio
async def test_get_many_full_batch_counts_outcome_full():
    batch = [MetricsMessage(value=i) for i in range(5)]
    consumer = QueueConsumer[MetricsMessage](
        backend=StaticBatchBackend(batch=batch), name="metrics-outcome-full"
    )
    await consumer.start()

    result = await consumer.get_many(5)

    assert result == batch
    outcome = _sample(
        "event_queue_get_many_outcomes_total",
        {"queue": "metrics-outcome-full", "outcome": "full"},
    )
    assert outcome == 1

    await consumer.stop()


@pytest.mark.asyncio
async def test_get_many_short_batch_counts_outcome_partial():
    batch = [MetricsMessage(value=i) for i in range(3)]
    consumer = QueueConsumer[MetricsMessage](
        backend=StaticBatchBackend(batch=batch), name="metrics-outcome-partial"
    )
    await consumer.start()

    result = await consumer.get_many(10)

    assert result == batch
    outcome = _sample(
        "event_queue_get_many_outcomes_total",
        {"queue": "metrics-outcome-partial", "outcome": "partial"},
    )
    assert outcome == 1

    await consumer.stop()


@pytest.mark.asyncio
async def test_get_many_empty_batch_counts_outcome_empty():
    consumer = QueueConsumer[MetricsMessage](
        backend=StaticBatchBackend(batch=[]), name="metrics-outcome-empty"
    )
    await consumer.start()

    result = await consumer.get_many(10)

    assert result == []
    outcome = _sample(
        "event_queue_get_many_outcomes_total",
        {"queue": "metrics-outcome-empty", "outcome": "empty"},
    )
    assert outcome == 1

    await consumer.stop()


@pytest.mark.asyncio
async def test_get_many_error_does_not_count_outcome():
    consumer = QueueConsumer[MetricsMessage](
        backend=StaticBatchBackend(batch=RuntimeError("backend down")),
        name="metrics-outcome-error",
    )
    await consumer.start()

    result = await consumer.get_many(10)

    assert isinstance(result, Exception)
    outcomes = _sample(
        "event_queue_get_many_outcomes_total",
        {"queue": "metrics-outcome-error", "outcome": "empty"},
    )
    assert outcomes is None

    await consumer.stop()
