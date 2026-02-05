import asyncio
from typing import Any, Callable
from unittest.mock import AsyncMock, Mock

import pytest
from bot_detector.worker import ConsumerWorker, ProducerWorker

from test.components.bot_detector.worker.kafka import (
    DummyProducer,
    DummyQueue,
    TestMessage,
)


# --- Test worker ---
class TestWorker(ConsumerWorker[TestMessage]):
    # overwrite the sleeps to speed up tests
    EMPTY_MESSAGE_SLEEP = 0

    def __init__(
        self,
        queue: DummyQueue,
        on_message_result: Callable[[TestMessage], Exception | None] | None = None,
        on_batch_result: Callable[[list[TestMessage]], Exception | None] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(queue=queue, **kwargs)
        self.seen_messages: list[TestMessage] = []
        self.seen_batches: list[list[TestMessage]] = []
        self._on_message_result = on_message_result or (lambda _: None)
        self._on_batch_result = on_batch_result or (lambda _: None)

    async def on_message(self, message: TestMessage) -> Exception | None:
        self.seen_messages.append(message)
        return self._on_message_result(message)

    async def on_message_batch(self, messages: list[TestMessage]) -> Exception | None:
        self.seen_batches.append(messages)
        return self._on_batch_result(messages)


# --- Tests ---
@pytest.mark.asyncio
async def test_worker_process_message_success():
    messages = [
        TestMessage(id="1", data="a"),
        TestMessage(id="2", data="b"),
    ]

    consumer_queue = [{"message": m} for m in messages]
    queue = DummyQueue(queue=consumer_queue)
    worker = TestWorker(
        queue=queue,
        batch_processing=False,
    )

    logger = Mock()
    worker._logger = logger

    # Run the worker
    task = asyncio.create_task(worker.start())

    # Wait until all messages are processed
    while len(worker.seen_messages) < len(messages):
        await asyncio.sleep(0)

    # Stop the worker
    await worker.stop()
    await task

    assert worker.seen_messages == messages
    queue.put.assert_not_called()
    queue.commit.assert_called()
    logger.error.assert_not_called()


@pytest.mark.asyncio
async def test_worker_retries_failed_message(monkeypatch):
    messages = [TestMessage(id="1", data="a"), TestMessage(id="2", data="b")]
    consumer_queue = [{"message": m} for m in messages]
    queue = DummyQueue(queue=consumer_queue)

    # Fail only message with id="2"
    def fail_on_message(msg: TestMessage) -> Exception | None:
        if msg.id == "2":
            return ValueError("failed")
        return None

    worker = TestWorker(queue=queue, on_message_result=fail_on_message)

    # Run the worker
    task = asyncio.create_task(worker.start())

    while len(worker.seen_messages) < len(messages):
        await asyncio.sleep(0)

    await worker.stop()
    await task

    queue.put.assert_called_once_with([messages[1]])
    queue.commit.assert_called()


@pytest.mark.asyncio
async def test_worker_batch_processing_retries_all(monkeypatch):
    messages = [TestMessage(id="1", data="a"), TestMessage(id="2", data="b")]
    consumer_queue = [{"message": m} for m in messages]
    queue = DummyQueue(queue=consumer_queue)
    worker = TestWorker(
        queue=queue,
        batch_processing=True,
        on_batch_result=lambda _: ValueError("failed"),
    )

    # Run the worker
    task = asyncio.create_task(worker.start())

    while len(worker.seen_batches) < 1:
        await asyncio.sleep(0)

    await worker.stop()
    await task

    assert worker.seen_batches == [messages]
    assert worker.seen_messages == []
    queue.put.assert_called_once_with(messages)
    queue.commit.assert_called()


@pytest.mark.asyncio
async def test_worker_logs_consumer_errors(monkeypatch):
    consumer_queue = [{"error": ValueError("oops")}]
    queue = DummyQueue(queue=consumer_queue)
    worker = TestWorker(queue=queue)

    logger = Mock()
    logger.info = Mock()
    logger.error = Mock()
    worker._logger = logger

    task = asyncio.create_task(worker.start())

    while not consumer_queue == []:
        await asyncio.sleep(0)

    await worker.stop()
    await task

    logger.error.assert_called()


@pytest.mark.asyncio
async def test_worker_start_stop_calls_dependencies():
    queue = DummyQueue()
    worker = TestWorker(queue=queue)

    worker._run = AsyncMock()  # prevent actual loop
    await worker.start()
    await worker.stop()

    queue.start.assert_called_once()
    worker._run.assert_called_once()
    queue.stop.assert_called_once()


class TestProducerWorker(ProducerWorker[TestMessage]):
    def __init__(
        self,
        queue: DummyProducer,
        batch: list[TestMessage] | None = None,
    ) -> None:
        super().__init__(queue=queue)
        self._batch = batch

    async def build_messages(self) -> list[TestMessage] | Exception | None:
        return self._batch


@pytest.mark.asyncio
async def test_producer_worker_puts_batch():
    producer = DummyProducer()
    worker = TestProducerWorker(
        queue=producer,
        batch=[TestMessage(id="1", data="a")],
    )
    worker._empty_message_hook = AsyncMock()
    task = asyncio.create_task(worker.start())
    while not producer.put.called:
        await asyncio.sleep(0)
    await worker.stop()
    await task
    producer.put.assert_called_once()
