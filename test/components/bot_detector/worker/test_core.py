import asyncio

import pytest
from bot_detector.event_queue.adapters.memory import InMemoryConfig
from bot_detector.event_queue.core import Queue
from bot_detector.event_queue.factory import QueueFactory
from bot_detector.worker.core import Worker, WorkerRunner
from bot_detector.worker.errors import WorkerError
from pydantic import BaseModel


class DummyMessage(BaseModel):
    value: int


class RecordingWorker(Worker[DummyMessage]):
    def __init__(self):
        self.batches: list[list[DummyMessage]] = []

    async def handle(self, batch: list[DummyMessage]) -> list[DummyMessage]:
        self.batches.append(batch)
        return []


class FailingWorker(Worker[DummyMessage]):
    async def handle(self, batch: list[DummyMessage]) -> list[DummyMessage]:
        raise RuntimeError("boom")


class ErrorReturningWorker(Worker[DummyMessage]):
    """Returns a WorkerError on the first batch, then succeeds on redelivery."""

    def __init__(self):
        self.first_batch: list[DummyMessage] = []
        self.processed: list[DummyMessage] = []
        self._saw_first = False

    async def handle(
        self, batch: list[DummyMessage]
    ) -> list[DummyMessage] | WorkerError[DummyMessage]:
        if not self._saw_first:
            self._saw_first = True
            self.first_batch = list(batch)
            return WorkerError(
                "transient insert failure",
                ok_batch=[],
                error_batch=list(batch),
            )
        self.processed.extend(batch)
        return []


class PartialErrorWorker(Worker[DummyMessage]):
    """Fails odd-valued items via WorkerError on first pass, succeeds after.

    Mimics a transient per-item failure: even values are reported as ok_batch
    (kept), odd values are reported as error_batch (requeued) and processed
    when they are redelivered.
    """

    def __init__(self):
        self.processed: list[DummyMessage] = []
        self._saw_first = False

    async def handle(
        self, batch: list[DummyMessage]
    ) -> list[DummyMessage] | WorkerError[DummyMessage]:
        ok = [m for m in batch if m.value % 2 == 0]
        failed = [m for m in batch if m.value % 2 == 1]
        if not self._saw_first:
            self._saw_first = True
            self.processed.extend(ok)
            return WorkerError(
                "partial insert failure",
                ok_batch=ok,
                error_batch=failed,
            )
        self.processed.extend(batch)
        return []


class PartialRequeueWorker(Worker[DummyMessage]):
    """Requeues odd-valued messages on the first batch, then succeeds fully.

    Mimics a transient per-item failure: the odd values are returned for requeue
    on the first pass and processed when they are redelivered.
    """

    def __init__(self):
        self.first_batch: list[DummyMessage] = []
        self.processed: list[DummyMessage] = []
        self._saw_first = False

    async def handle(self, batch: list[DummyMessage]) -> list[DummyMessage]:
        if not self._saw_first:
            self._saw_first = True
            self.first_batch = list(batch)
            self.processed.extend(m for m in batch if m.value % 2 == 0)
            return [m for m in batch if m.value % 2 == 1]
        self.processed.extend(batch)
        return []


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
        worker_name="test",
        stop_event=asyncio.Event(),
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
        worker_name="test",
        stop_event=asyncio.Event(),
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
async def test_worker_runner_requeues_on_worker_error():
    worker = ErrorReturningWorker()
    queue = _create_queue([])
    await queue.start()
    await queue.put([DummyMessage(value=i) for i in range(3)])

    runner = WorkerRunner(
        config=InMemoryConfig(maxsize=100),
        model=DummyMessage,
        worker=worker,
        worker_name="test",
        stop_event=asyncio.Event(),
        batch_size=10,
    )
    runner._queue = queue

    task = asyncio.create_task(runner._consume())
    await asyncio.sleep(1.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # The whole batch was requeued on WorkerError and redelivered, then processed.
    assert {m.value for m in worker.first_batch} == {0, 1, 2}
    assert {m.value for m in worker.processed} == {0, 1, 2}
    leftover = await queue.get_many(10)
    assert leftover == []

    await queue.stop()


@pytest.mark.asyncio
async def test_worker_runner_requeues_only_error_batch():
    worker = PartialErrorWorker()
    queue = _create_queue([])
    await queue.start()
    await queue.put([DummyMessage(value=i) for i in range(4)])  # 0, 1, 2, 3

    runner = WorkerRunner(
        config=InMemoryConfig(maxsize=100),
        model=DummyMessage,
        worker=worker,
        worker_name="test",
        stop_event=asyncio.Event(),
        batch_size=10,
    )
    runner._queue = queue

    task = asyncio.create_task(runner._consume())
    await asyncio.sleep(1.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # ok_batch ([0, 2]) was kept; only error_batch ([1, 3]) was requeued and
    # redelivered, then processed. All values end up processed exactly once.
    assert {m.value for m in worker.processed} == {0, 1, 2, 3}
    leftover = await queue.get_many(10)
    assert leftover == []

    await queue.stop()


@pytest.mark.asyncio
async def test_worker_runner_requeues_only_returned_subset():
    worker = PartialRequeueWorker()
    queue = _create_queue([])
    await queue.start()
    await queue.put([DummyMessage(value=i) for i in range(4)])  # 0, 1, 2, 3

    runner = WorkerRunner(
        config=InMemoryConfig(maxsize=100),
        model=DummyMessage,
        worker=worker,
        worker_name="test",
        stop_event=asyncio.Event(),
        batch_size=10,
    )
    runner._queue = queue

    task = asyncio.create_task(runner._consume())
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # First batch received all 4 messages; even values processed, odd returned.
    assert {m.value for m in worker.first_batch} == {0, 1, 2, 3}
    # The requeued odd values were redelivered and processed on the second pass.
    assert {m.value for m in worker.processed} == {0, 1, 2, 3}
    # Queue is fully drained — only the returned subset was requeued, not all 4.
    leftover = await queue.get_many(10)
    assert leftover == []

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
        worker_name="test",
        stop_event=asyncio.Event(),
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
        worker_name="test",
        stop_event=asyncio.Event(),
        batch_size=10,
    )

    task = asyncio.create_task(runner.run())
    await asyncio.sleep(0.1)
    task.cancel()
    await task

    assert task.done()
