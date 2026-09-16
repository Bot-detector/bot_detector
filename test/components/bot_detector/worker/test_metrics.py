import asyncio

import pytest
from bot_detector.event_queue.adapters.memory import InMemoryConfig
from bot_detector.event_queue.factory import QueueFactory
from bot_detector.worker.core import Worker, WorkerRunner
from bot_detector.worker.errors import WorkerError
from prometheus_client import REGISTRY
from pydantic import BaseModel


class MetricsMessage(BaseModel):
    value: int


def _sample(name: str, labels: dict[str, str]) -> float | None:
    return REGISTRY.get_sample_value(name, labels)


class OkWorker(Worker[MetricsMessage]):
    async def handle(self, batch: list[MetricsMessage]) -> list[MetricsMessage]:
        return []


class FailingWorker(Worker[MetricsMessage]):
    async def handle(self, batch: list[MetricsMessage]) -> list[MetricsMessage]:
        raise RuntimeError("boom")


class WorkerErrorWorker(Worker[MetricsMessage]):
    async def handle(
        self, batch: list[MetricsMessage]
    ) -> list[MetricsMessage] | WorkerError[MetricsMessage]:
        return WorkerError(
            "transient failure",
            ok_batch=[],
            error_batch=list(batch),
        )


def _create_runner(
    worker: Worker[MetricsMessage], name: str
) -> tuple[WorkerRunner[MetricsMessage], object]:
    queue = QueueFactory.create_queue(
        model=MetricsMessage,
        queue_type="queue",
        backend_type="memory",
        config=InMemoryConfig(maxsize=100),
    )
    assert not isinstance(queue, Exception)
    runner = WorkerRunner(
        config=InMemoryConfig(maxsize=100),
        model=MetricsMessage,
        worker=worker,
        stop_event=asyncio.Event(),
        batch_size=10,
        name=name,
    )
    runner._queue = queue
    return runner, queue


async def _consume_briefly(runner: WorkerRunner[MetricsMessage], seconds: float):
    task = asyncio.create_task(runner._consume())
    await asyncio.sleep(seconds)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_runner_counts_consumed_batches_and_messages():
    runner, queue = _create_runner(OkWorker(), name="metrics-ok")
    await queue.start()
    await queue.put([MetricsMessage(value=i) for i in range(3)])

    await _consume_briefly(runner, 0.2)

    batches = _sample("worker_batches_consumed_total", {"worker": "metrics-ok"})
    messages = _sample("worker_messages_consumed_total", {"worker": "metrics-ok"})
    handle_count = _sample("worker_handle_seconds_count", {"worker": "metrics-ok"})
    assert batches is not None and batches >= 1
    assert messages is not None and messages >= 3
    assert handle_count is not None and handle_count >= 1

    await queue.stop()


@pytest.mark.asyncio
async def test_runner_counts_requeued_messages_on_worker_error():
    runner, queue = _create_runner(WorkerErrorWorker(), name="metrics-werror")
    await queue.start()
    await queue.put([MetricsMessage(value=i) for i in range(2)])

    await _consume_briefly(runner, 0.3)

    requeued = _sample("worker_messages_requeued_total", {"worker": "metrics-werror"})
    assert requeued is not None and requeued >= 2

    await queue.stop()


@pytest.mark.asyncio
async def test_runner_counts_handle_errors():
    runner, queue = _create_runner(FailingWorker(), name="metrics-fail")
    await queue.start()
    await queue.put([MetricsMessage(value=i) for i in range(2)])

    await _consume_briefly(runner, 0.3)

    errors = _sample(
        "worker_errors_total", {"worker": "metrics-fail", "kind": "handle"}
    )
    requeued = _sample("worker_messages_requeued_total", {"worker": "metrics-fail"})
    assert errors is not None and errors >= 1
    assert requeued is not None and requeued >= 2

    await queue.stop()
