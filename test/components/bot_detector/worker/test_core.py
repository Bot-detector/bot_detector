import asyncio

import pytest
from bot_detector.event_queue.adapters.memory import InMemoryConfig
from bot_detector.event_queue.core import Queue
from bot_detector.event_queue.factory import QueueFactory
from bot_detector.worker.core import Worker, WorkerRunner
from pydantic import BaseModel


class DummyMessage(BaseModel):
    value: int


class RecordingWorker(Worker[DummyMessage]):
    def __init__(self):
        self.batches: list[list[DummyMessage]] = []

    async def handle(self, batch: list[DummyMessage]) -> None:
        self.batches.append(batch)


class FailingWorker(Worker[DummyMessage]):
    async def handle(self, batch: list[DummyMessage]) -> None:
        raise RuntimeError("boom")


def _create_queue(messages: list[DummyMessage]) -> Queue[DummyMessage]:
    queue = QueueFactory.create_queue(
        model=DummyMessage,
        queue_type="queue",
        backend_type="memory",
        config=InMemoryConfig(maxsize=100),
    )
    assert isinstance(queue, Queue)
    return queue


@pytest.mark.asyncio
async def test_worker_runner_processes_batch():
    worker = RecordingWorker()
    queue = _create_queue([])
    await queue.start()
    await queue.put([DummyMessage(value=i) for i in range(5)])

    runner = WorkerRunner(
        config=InMemoryConfig(maxsize=100),
        model=DummyMessage,
        worker=worker,
        batch_size=10,
    )
    runner._queue = queue

    task = asyncio.create_task(runner._consume())
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert len(worker.batches) == 1
    assert len(worker.batches[0]) == 5


@pytest.mark.asyncio
async def test_worker_runner_requeues_on_error():
    worker = FailingWorker()
    queue = _create_queue([])
    await queue.start()
    messages = [DummyMessage(value=i) for i in range(3)]
    await queue.put(messages)

    runner = WorkerRunner(
        config=InMemoryConfig(maxsize=100),
        model=DummyMessage,
        worker=worker,
        batch_size=10,
    )
    runner._queue = queue

    task = asyncio.create_task(runner._consume())
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    requeued = await queue.get_many(10)
    assert not isinstance(requeued, Exception)
    assert len(requeued) == 3

    await queue.stop()


@pytest.mark.asyncio
async def test_worker_runner_skips_empty_batch():
    worker = RecordingWorker()
    queue = _create_queue([])
    await queue.start()

    runner = WorkerRunner(
        config=InMemoryConfig(maxsize=100),
        model=DummyMessage,
        worker=worker,
        batch_size=10,
    )
    runner._queue = queue

    task = asyncio.create_task(runner._consume())
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert len(worker.batches) == 0

    await queue.stop()


@pytest.mark.asyncio
async def test_worker_runner_graceful_shutdown():
    worker = RecordingWorker()
    runner = WorkerRunner(
        config=InMemoryConfig(maxsize=100),
        model=DummyMessage,
        worker=worker,
        batch_size=10,
    )

    task = asyncio.create_task(runner.run())
    await asyncio.sleep(0.1)
    task.cancel()
    await task

    assert task.done()
