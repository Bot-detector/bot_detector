import asyncio
from typing import Any, Callable
from unittest.mock import AsyncMock, Mock

import pytest
from bot_detector.worker import BaseWorker

from test.components.bot_detector.worker.kafka import (
    DummyConsumer,
    DummyProducer,
    TestMessage,
)


# --- Test worker ---
class TestWorker(BaseWorker[TestMessage]):
    # overwrite the sleeps to speed up tests
    EMPTY_MESSAGE_SLEEP = 0
    PRODUCE_RETRY_DELAY = 0
    PRODUCE_MAX_RETRY = 3

    def __init__(
        self,
        *args: Any,
        on_message_result: Callable[[TestMessage], bool] | None = None,
        on_batch_result: Callable[[list[TestMessage]], bool] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.seen_messages: list[TestMessage] = []
        self.seen_batches: list[list[TestMessage]] = []
        self._on_message_result = on_message_result or (lambda _: True)
        self._on_batch_result = on_batch_result or (lambda _: True)

    async def on_message(self, message: TestMessage) -> bool:
        self.seen_messages.append(message)
        return self._on_message_result(message)

    async def on_message_batch(self, messages: list[TestMessage]) -> bool:
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
    consumer = DummyConsumer(queue=consumer_queue)
    producer = DummyProducer()

    worker = TestWorker(
        consumer=consumer,
        producer=producer,
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
    producer.produce_one.assert_not_called()
    consumer.commit.assert_called()
    logger.error.assert_not_called()


@pytest.mark.asyncio
async def test_worker_retries_failed_message(monkeypatch):
    messages = [TestMessage(id="1", data="a"), TestMessage(id="2", data="b")]
    consumer_queue = [{"message": m} for m in messages]
    consumer = DummyConsumer(queue=consumer_queue)
    producer = DummyProducer()

    # Fail only message with id="2"
    def fail_on_message(msg: TestMessage) -> bool:
        return msg.id != "2"

    worker = TestWorker(
        consumer=consumer,
        producer=producer,
        on_message_result=fail_on_message,
    )

    # Run the worker
    task = asyncio.create_task(worker.start())

    while len(worker.seen_messages) < len(messages):
        await asyncio.sleep(0)

    await worker.stop()
    await task

    producer.produce_one.assert_called_once_with(message=messages[1])
    consumer.commit.assert_called()


@pytest.mark.asyncio
async def test_worker_batch_processing_retries_all(monkeypatch):
    messages = [TestMessage(id="1", data="a"), TestMessage(id="2", data="b")]
    consumer_queue = [{"message": m} for m in messages]
    consumer = DummyConsumer(queue=consumer_queue)
    producer = DummyProducer()

    worker = TestWorker(
        consumer=consumer,
        producer=producer,
        batch_processing=True,
        on_batch_result=lambda _: False,
    )

    # Run the worker
    task = asyncio.create_task(worker.start())

    while len(worker.seen_batches) < 1:
        await asyncio.sleep(0)

    await worker.stop()
    await task

    assert worker.seen_batches == [messages]
    assert worker.seen_messages == []
    assert producer.produce_one.call_count == len(messages)
    consumer.commit.assert_called()


@pytest.mark.asyncio
async def test_worker_logs_consumer_errors(monkeypatch):
    consumer_queue = [{"error": "oops"}]
    consumer = DummyConsumer(queue=consumer_queue)
    producer = DummyProducer()
    worker = TestWorker(consumer=consumer, producer=producer)

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
    consumer = DummyConsumer()
    producer = DummyProducer()
    worker = TestWorker(consumer=consumer, producer=producer)

    worker._run = AsyncMock()  # prevent actual loop
    await worker.start()
    await worker.stop()

    consumer.start.assert_called_once()
    producer.start.assert_called_once()
    worker._run.assert_called_once()
    consumer.stop.assert_called_once()
    producer.stop.assert_called_once()
