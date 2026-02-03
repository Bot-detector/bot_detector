import asyncio
from typing import Any, Optional
from unittest.mock import AsyncMock

import pytest
from bot_detector.kafka import ConsumerInterface, ProducerInterface
from bot_detector.worker import BaseWorker
from bot_detector.worker.interface import WorkerInterface
from pydantic import BaseModel

# ===== Mock Data Models =====


class TestMessage(BaseModel):
    """Simple Pydantic model for testing."""

    id: str
    data: str


# ===== Mock Consumer & Producer =====
class MockConsumer(ConsumerInterface[TestMessage]):
    """Mock consumer for testing Worker."""

    def __init__(self) -> None:
        self._started = False
        self._stopped = False
        self._messages: list[TestMessage] = []
        self._commit_count = 0
        self._start_count = 0
        self._stop_count = 0
        self.consume_many = AsyncMock(return_value=([], []))  # type: ignore[assignment]

    async def start(self) -> None:
        self._started = True
        self._start_count += 1

    async def stop(self) -> None:
        self._stopped = True
        self._stop_count += 1

    async def get_consumer(self) -> Any:
        return None

    async def consume_one(self) -> tuple[Optional[TestMessage], Optional[str]]:
        return None, None

    async def get_lag(self) -> int:
        return 0

    async def commit(self) -> None:
        """Mock commit method."""
        self._commit_count += 1


class MockProducer(ProducerInterface[TestMessage]):
    """Mock producer for testing Worker."""

    def __init__(self) -> None:
        self._started = False
        self._stopped = False
        self._produced: list[TestMessage] = []
        self._start_count = 0
        self._stop_count = 0
        self._side_effect_produce_one: Any = None

    async def start(self) -> None:
        self._started = True
        self._start_count += 1

    async def stop(self) -> None:
        self._stopped = True
        self._stop_count += 1

    async def get_producer(self) -> Any:
        return None

    async def produce_one(
        self,
        message: TestMessage,
        topic: Optional[str] = None,
        partition_key: Optional[bytes] = None,
        max_retries: int = 5,
    ) -> None:
        """Track produced messages for testing."""
        self._produced.append(message)
        if self._side_effect_produce_one:
            await self._side_effect_produce_one(
                message, topic, partition_key, max_retries
            )


# ===== Protocol Compliance Tests =====


def test_worker_interface_protocol():
    """Test that BaseWorker implements WorkerInterface."""
    consumer = MockConsumer()
    producer = MockProducer()
    worker = BaseWorker[TestMessage](consumer, producer)

    # Verify protocol compliance
    assert isinstance(worker, WorkerInterface)


# ===== Initialization Tests =====


@pytest.mark.asyncio
async def test_worker_initialization():
    """Test worker initialization with default parameters."""
    consumer = MockConsumer()
    producer = MockProducer()

    worker = BaseWorker[TestMessage](consumer, producer)
    assert worker._consumer == consumer
    assert worker._producer == producer
    assert worker._max_messages == 10_000
    assert worker._max_interval_ms == 5_000
    assert worker._batch_processing is False
    assert worker._batch_size == 1
    assert worker._sample_ratio == 0.01


@pytest.mark.asyncio
async def test_worker_custom_initialization():
    """Test worker initialization with custom parameters."""
    consumer = MockConsumer()
    producer = MockProducer()

    worker = BaseWorker[TestMessage](
        consumer,
        producer,
        max_messages=100,
        max_interval_ms=2000,
        batch_processing=True,
        batch_size=50,
        sample_ratio=0.05,
    )
    assert worker._max_messages == 100
    assert worker._max_interval_ms == 2000
    assert worker._batch_processing is True
    assert worker._batch_size == 50
    assert worker._sample_ratio == 0.05


# ===== Lifecycle Tests =====


@pytest.mark.asyncio
async def test_worker_start_stop():
    """Test worker start and stop lifecycle."""
    consumer = MockConsumer()
    producer = MockProducer()

    class TestWorker(BaseWorker[TestMessage]):
        async def on_message(self, message: TestMessage) -> bool:
            return True

    worker = TestWorker(consumer, producer)
    worker._consumer.consume_many = AsyncMock(return_value=([], None))

    # Start worker
    start_task = asyncio.create_task(worker.start())
    await asyncio.sleep(0.1)  # Let worker start

    assert consumer._started is True
    assert producer._started is True

    # Stop worker
    start_task.cancel()
    try:
        await start_task
    except asyncio.CancelledError:
        pass

    await worker.stop()
    assert consumer._stopped is True
    assert producer._stopped is True


# ===== Single Message Processing Tests =====


@pytest.mark.asyncio
async def test_single_message_processing():
    """Test processing of single messages."""
    consumer = MockConsumer()
    producer = MockProducer()

    class TestWorker(BaseWorker[TestMessage]):
        def __init__(self, consumer, producer):
            super().__init__(consumer, producer)
            self.processed_messages: list[TestMessage] = []

        async def on_message(self, message: TestMessage) -> bool:
            self.processed_messages.append(message)
            return True

    worker = TestWorker(consumer, producer)
    messages = [
        TestMessage(id="1", data="test1"),
        TestMessage(id="2", data="test2"),
    ]

    # Mock consumer to return messages then empty
    consume_count = [0]

    async def mock_consume(*args, **kwargs):
        if consume_count[0] < 1:
            consume_count[0] += 1
            return messages, None
        return [], None

    worker._consumer.consume_many = mock_consume

    # Run worker briefly
    task = asyncio.create_task(worker.start())
    await asyncio.sleep(0.2)
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass

    await worker.stop()

    # Verify processing
    assert len(worker.processed_messages) == 2
    assert worker.processed_messages[0].id == "1"
    assert worker.processed_messages[1].id == "2"


# ===== Batch Processing Tests =====


@pytest.mark.asyncio
async def test_batch_processing():
    """Test batch message processing."""
    consumer = MockConsumer()
    producer = MockProducer()

    class TestWorker(BaseWorker[TestMessage]):
        def __init__(self, consumer, producer, batch_processing, batch_size):
            super().__init__(
                consumer,
                producer,
                batch_processing=batch_processing,
                batch_size=batch_size,
            )
            self.processed_batches: list[list[TestMessage]] = []

        async def on_message_batch(self, messages: list[TestMessage]) -> bool:
            self.processed_batches.append(messages.copy())
            return True

    worker = TestWorker(consumer, producer, batch_processing=True, batch_size=2)
    messages = [
        TestMessage(id="1", data="test1"),
        TestMessage(id="2", data="test2"),
        TestMessage(id="3", data="test3"),
        TestMessage(id="4", data="test4"),
    ]

    # Mock consumer to return messages then empty
    consume_count = [0]

    async def mock_consume(*args, **kwargs):
        if consume_count[0] < 1:
            consume_count[0] += 1
            return messages, None
        return [], None

    worker._consumer.consume_many = mock_consume

    # Run worker briefly
    task = asyncio.create_task(worker.start())
    await asyncio.sleep(0.2)
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass

    await worker.stop()

    # Verify batch processing - worker processes the whole batch at once
    assert len(worker.processed_batches) == 1
    assert len(worker.processed_batches[0]) == 4


# ===== Failure & Retry Tests =====


@pytest.mark.asyncio
async def test_message_failure_and_retry():
    """Test that failed messages are retried."""
    consumer = MockConsumer()
    producer = MockProducer()

    class TestWorker(BaseWorker[TestMessage]):
        def __init__(self, consumer, producer):
            super().__init__(consumer, producer)
            self.processed_messages: list[TestMessage] = []
            self.failed_messages: list[TestMessage] = []

        async def on_message(self, message: TestMessage) -> bool:
            self.processed_messages.append(message)
            if message.id == "2":
                self.failed_messages.append(message)
                return False  # Fail this message
            return True

    worker = TestWorker(consumer, producer)
    messages = [
        TestMessage(id="1", data="test1"),
        TestMessage(id="2", data="test2"),
        TestMessage(id="3", data="test3"),
    ]

    # Mock consumer to return messages then empty
    consume_count = [0]

    async def mock_consume(*args, **kwargs):
        if consume_count[0] < 1:
            consume_count[0] += 1
            return messages, None
        return [], None

    worker._consumer.consume_many = mock_consume

    # Run worker briefly
    task = asyncio.create_task(worker.start())
    await asyncio.sleep(0.2)
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass

    await worker.stop()

    # Verify processing
    assert len(worker.processed_messages) == 3
    assert len(worker.failed_messages) == 1

    # Verify failed message was retried (produced by producer)
    assert len(producer._produced) == 1
    assert producer._produced[0].id == "2"


# ===== Empty Batch Tests =====


@pytest.mark.asyncio
async def test_empty_batch_handling():
    """Test handling of empty batches."""
    consumer = MockConsumer()
    producer = MockProducer()

    class TestWorker(BaseWorker[TestMessage]):
        async def on_message(self, message: TestMessage) -> bool:
            return True

    worker = TestWorker(consumer, producer)

    # Mock consumer to always return empty batch
    async def mock_consume(*args, **kwargs):
        return [], None

    worker._consumer.consume_many = mock_consume

    # Run worker briefly
    task = asyncio.create_task(worker.start())
    await asyncio.sleep(0.2)  # Let worker run and sleep
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass

    await worker.stop()

    # Should start consumer even with no messages
    assert consumer._started is True


# ===== Consumer Error Handling Tests =====


@pytest.mark.asyncio
async def test_consumer_error_handling():
    """Test error handling when consumer fails."""
    consumer = MockConsumer()
    producer = MockProducer()

    class TestWorker(BaseWorker[TestMessage]):
        async def on_message(self, message: TestMessage) -> bool:
            return True

    worker = TestWorker(consumer, producer)

    # Make consumer raise error
    async def failing_consume(*args, **kwargs):
        raise Exception("Consumer error")

    worker._consumer.consume_many = failing_consume

    # Run worker briefly
    task = asyncio.create_task(worker.start())
    await asyncio.sleep(0.2)  # Let worker run, encounter error, and sleep
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass

    await worker.stop()

    # Should start consumer despite errors
    assert consumer._started is True


# ===== Producer Error Handling Tests =====


@pytest.mark.asyncio
async def test_producer_error_handling():
    """Test error handling when producer fails."""
    consumer = MockConsumer()
    producer = MockProducer()

    class TestWorker(BaseWorker[TestMessage]):
        def __init__(self, consumer, producer):
            super().__init__(consumer, producer)
            self.processed_messages: list[TestMessage] = []

        async def on_message(self, message: TestMessage) -> bool:
            self.processed_messages.append(message)
            return True

    worker = TestWorker(consumer, producer)

    # Make producer raise error
    async def failing_produce(*args, **kwargs):
        raise Exception("Producer error")

    producer.produce_one = failing_produce

    messages = [
        TestMessage(id="1", data="test1"),
        TestMessage(id="2", data="test2"),
    ]

    # Mock consumer to return messages with some failures
    consume_count = [0]

    async def mock_consume(*args, **kwargs):
        if consume_count[0] < 1:
            consume_count[0] += 1
            return messages, None
        return [], None

    worker._consumer.consume_many = mock_consume

    # Run worker briefly
    task = asyncio.create_task(worker.start())
    await asyncio.sleep(0.2)
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass

    await worker.stop()

    # Messages should still be processed
    assert len(worker.processed_messages) == 2


# ===== on_message_batch Fallback Tests =====


@pytest.mark.asyncio
async def test_on_message_batch_not_implemented():
    """Test batch processing without on_message_batch implementation."""
    consumer = MockConsumer()
    producer = MockProducer()

    class TestWorker(BaseWorker[TestMessage]):
        def __init__(self, consumer, producer, batch_processing, batch_size):
            super().__init__(
                consumer,
                producer,
                batch_processing=batch_processing,
                batch_size=batch_size,
            )
            self.processed_messages: list[TestMessage] = []

        async def on_message(self, message: TestMessage) -> bool:
            self.processed_messages.append(message)
            return True

    worker = TestWorker(consumer, producer, batch_processing=True, batch_size=2)

    messages = [
        TestMessage(id="1", data="test1"),
        TestMessage(id="2", data="test2"),
    ]

    # Mock consumer to return messages then empty
    consume_count = [0]

    async def mock_consume(*args, **kwargs):
        if consume_count[0] < 1:
            consume_count[0] += 1
            return messages, None
        return [], None

    worker._consumer.consume_many = mock_consume

    # Run worker briefly
    task = asyncio.create_task(worker.start())
    await asyncio.sleep(0.2)
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass

    await worker.stop()

    # Should process all messages using default on_message_batch implementation
    assert len(worker.processed_messages) == 2


# ===== Sample Ratio Tests =====


@pytest.mark.asyncio
async def test_error_based_logging_errors_always_logged():
    """Test that errors are always logged regardless of sample_ratio."""
    from unittest.mock import patch

    consumer = MockConsumer()
    producer = MockProducer()

    class TestWorker(BaseWorker[TestMessage]):
        def __init__(self, consumer, producer, sample_ratio):
            super().__init__(consumer, producer, sample_ratio=sample_ratio)
            self.last_context: dict = {}

        async def on_message(self, message: TestMessage) -> bool:
            return True

        def _log(self) -> None:
            """Capture last context for testing."""
            context = self._get_context()
            if context:  # Only capture non-empty contexts
                self.last_context = context
            super()._log()

    # Very low sample_ratio - errors should still be logged
    worker = TestWorker(consumer, producer, sample_ratio=0.000001)

    messages = [TestMessage(id="1", data="test1")]

    # Mock consumer to return messages then empty
    consume_count = [0]

    async def mock_consume(*args, **kwargs):
        if consume_count[0] < 1:
            consume_count[0] += 1
            # Return error with batch
            return messages, ["Consumer error"]
        return [], []

    worker._consumer.consume_many = mock_consume

    # Mock sleep to avoid delay
    sleep_calls = []
    original_sleep = asyncio.sleep

    async def mock_sleep(seconds):
        sleep_calls.append(seconds)
        # Test delays (<5) actually sleep, worker delays (>=5) yield briefly
        if seconds < 5:
            await original_sleep(0.01)
        else:
            # Worker delays - very brief yield to allow other tasks to run
            await original_sleep(0)

    # Run worker briefly
    with patch("asyncio.sleep", side_effect=mock_sleep):
        task = asyncio.create_task(worker.start())
        await asyncio.sleep(0.2)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        await worker.stop()

    # Verify error context was set (errors always logged)
    context = worker.last_context
    assert "error" in context
    assert "consumer" in context["error"]


@pytest.mark.asyncio
async def test_error_based_logging_successes_sampled():
    """Test that successful messages are sampled based on sample_ratio."""
    from unittest.mock import patch

    consumer = MockConsumer()
    producer = MockProducer()

    class TestWorker(BaseWorker[TestMessage]):
        def __init__(self, consumer, producer, sample_ratio):
            super().__init__(consumer, producer, sample_ratio=sample_ratio)
            self.last_context: dict = {}

        async def on_message(self, message: TestMessage) -> bool:
            return True

        def _log(self) -> None:
            """Capture last context for testing."""
            context = self._get_context()
            if context:  # Only capture non-empty contexts
                self.last_context = context
            super()._log()

    # High sample_ratio (100%) to ensure sampling
    worker = TestWorker(consumer, producer, sample_ratio=1.0)

    messages = [TestMessage(id="1", data="test1")]

    # Mock consumer to return messages then empty
    consume_count = [0]

    async def mock_consume(*args, **kwargs):
        if consume_count[0] < 1:
            consume_count[0] += 1
            return messages, []
        return [], []

    worker._consumer.consume_many = mock_consume

    # Mock sleep to avoid delay
    sleep_calls = []
    original_sleep = asyncio.sleep

    async def mock_sleep(seconds):
        sleep_calls.append(seconds)
        # Test delays (<5) actually sleep, worker delays (>=5) yield briefly
        if seconds < 5:
            await original_sleep(0.01)
        else:
            # Worker delays - very brief yield to allow other tasks to run
            await original_sleep(0)

    # Run worker briefly
    with patch("asyncio.sleep", side_effect=mock_sleep):
        task = asyncio.create_task(worker.start())
        await asyncio.sleep(0.2)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        await worker.stop()

    # Verify context was set (successes sampled)
    context = worker.last_context
    assert "_run" in context


# ===== Commit Behavior Tests =====


@pytest.mark.asyncio
async def test_commit_called_after_processing():
    """Test that commit is called after successful processing."""
    from unittest.mock import patch

    consumer = MockConsumer()
    producer = MockProducer()

    class TestWorker(BaseWorker[TestMessage]):
        async def on_message(self, message: TestMessage) -> bool:
            return True

    worker = TestWorker(consumer, producer)

    messages = [
        TestMessage(id="1", data="test1"),
        TestMessage(id="2", data="test2"),
    ]

    # Mock consumer to return messages then empty
    consume_count = [0]

    async def mock_consume(*args, **kwargs):
        if consume_count[0] < 1:
            consume_count[0] += 1
            return messages, []
        return [], []

    worker._consumer.consume_many = mock_consume

    # Mock sleep to avoid delay
    async def mock_sleep(seconds):
        # Don't actually sleep - just return to allow event loop to process
    async def mock_sleep(seconds):
        sleep_calls = []
        original_sleep = asyncio.sleep
        sleep_calls.append(seconds)
        # Test delays (<5) actually sleep, worker delays (>=5) yield briefly
        if seconds < 5:
            await original_sleep(0.01)
        else:
            # Worker delays - very brief yield to allow other tasks to run
            await original_sleep(0)

    # Run worker briefly
    with patch("asyncio.sleep", side_effect=mock_sleep):
        task = asyncio.create_task(worker.start())
        await asyncio.sleep(0.2)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        await worker.stop()

    # Verify commit was called after processing
    assert consumer._commit_count >= 1


@pytest.mark.asyncio
async def test_commit_not_called_on_empty_batch():
    """Test that commit is not called when batch is empty."""
    from unittest.mock import patch

    consumer = MockConsumer()
    producer = MockProducer()

    class TestWorker(BaseWorker[TestMessage]):
        async def on_message(self, message: TestMessage) -> bool:
            return True

    worker = TestWorker(consumer, producer)

    # Mock consumer to always return empty batch
    async def mock_consume(*args, **kwargs):
        return [], []

    worker._consumer.consume_many = mock_consume

    # Mock sleep to avoid delay
    sleep_calls = []
    original_sleep = asyncio.sleep

    async def mock_sleep(seconds):
        sleep_calls.append(seconds)
        # Test delays (<5) actually sleep, worker delays (>=5) yield briefly
        if seconds < 5:
            await original_sleep(0.01)
        else:
            # Worker delays - very brief yield to allow other tasks to run
            await original_sleep(0)

    # Run worker briefly
    with patch("asyncio.sleep", side_effect=mock_sleep):
        task = asyncio.create_task(worker.start())
        await asyncio.sleep(0.2)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        await worker.stop()

    # Verify commit was not called for empty batch
    assert consumer._commit_count == 0


# ===== Sleep Interval Tests =====


@pytest.mark.asyncio
async def test_sleep_after_retry():
    """Test that worker sleeps 15 seconds after retry."""
    from unittest.mock import patch

    consumer = MockConsumer()
    producer = MockProducer()

    class TestWorker(BaseWorker[TestMessage]):
        async def on_message(self, message: TestMessage) -> bool:
            if message.id == "2":
                return False  # Fail this message
            return True

    worker = TestWorker(consumer, producer)

    messages = [
        TestMessage(id="1", data="test1"),
        TestMessage(id="2", data="test2"),
    ]

    # Mock consumer to return messages then empty
    consume_count = [0]

    async def mock_consume(*args, **kwargs):
        if consume_count[0] < 1:
            consume_count[0] += 1
            return messages, []
        return [], []

    worker._consumer.consume_many = mock_consume

    # Track sleep calls by patching asyncio.sleep
    sleep_calls = []

    async def mock_sleep(seconds):
        sleep_calls.append(seconds)
        # Use sleep(0) to allow other coroutines to run without causing recursion
        # when asyncio.sleep is patched
        return None

    # Run worker briefly
    with patch("asyncio.sleep", side_effect=mock_sleep):
        task = asyncio.create_task(worker.start())
        await asyncio.sleep(0.2)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        await worker.stop()

    # Verify 15-second sleep after retry
    assert 15 in sleep_calls


@pytest.mark.asyncio
async def test_sleep_for_small_batches():
    """Test that worker sleeps 60 seconds for small batches."""
    from unittest.mock import patch

    consumer = MockConsumer()
    producer = MockProducer()

    class TestWorker(BaseWorker[TestMessage]):
        async def on_message(self, message: TestMessage) -> bool:
            return True

    worker = TestWorker(consumer, producer)

    # Small batch (< 1000)
    messages = [TestMessage(id="1", data="test1")]

    # Mock consumer to return messages then empty
    consume_count = [0]

    async def mock_consume(*args, **kwargs):
        if consume_count[0] < 1:
            consume_count[0] += 1
            return messages, []
        return [], []

    worker._consumer.consume_many = mock_consume

    # Track sleep calls
    sleep_calls = []

    async def mock_sleep(seconds):
        sleep_calls.append(seconds)
        # Use sleep(0) to allow other coroutines to run without causing recursion
        # when asyncio.sleep is patched
        return None

    # Run worker briefly
    with patch("asyncio.sleep", side_effect=mock_sleep):
        task = asyncio.create_task(worker.start())
        await asyncio.sleep(0.2)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        await worker.stop()

    # Verify 60-second sleep for small batch
    assert 60 in sleep_calls


@pytest.mark.asyncio
async def test_no_sleep_for_large_batches():
    """Test that worker does not sleep for large batches."""
    consumer = MockConsumer()
    producer = MockProducer()

    class TestWorker(BaseWorker[TestMessage]):
        async def on_message(self, message: TestMessage) -> bool:
            return True

    worker = TestWorker(consumer, producer)

    # Large batch (>= 1000)
    messages = [TestMessage(id=str(i), data=f"test{i}") for i in range(1000)]

    # Mock consumer to return messages then empty
    consume_count = [0]

    async def mock_consume(*args, **kwargs):
        if consume_count[0] < 1:
            consume_count[0] += 1
            return messages, None
        return [], None

    worker._consumer.consume_many = mock_consume

    # Track sleep calls
    sleep_calls = []

    async def mock_sleep(seconds):
        sleep_calls.append(seconds)
        # Cap sleeps to tiny amounts to allow worker to run quickly
        if seconds >= 15:
            await asyncio.sleep(0.001)
        elif seconds >= 60:
            await asyncio.sleep(0.001)
        else:
            await asyncio.sleep(0.0001)

    worker._sleep = mock_sleep

    # Run worker briefly
    task = asyncio.create_task(worker.start())
    await asyncio.sleep(0.2)
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass

    await worker.stop()

    # Verify no 60-second sleep for large batch
    assert 60 not in sleep_calls


@pytest.mark.asyncio
async def test_sleep_after_exception():
    """Test that worker sleeps 15 seconds after exception."""
    from unittest.mock import patch

    consumer = MockConsumer()
    producer = MockProducer()

    class TestWorker(BaseWorker[TestMessage]):
        async def on_message(self, message: TestMessage) -> bool:
            return True

    worker = TestWorker(consumer, producer)

    # Make consumer raise exception
    async def failing_consume(*args, **kwargs):
        raise Exception("Consumer error")

    worker._consumer.consume_many = failing_consume

    # Track sleep calls
    sleep_calls = []

    async def mock_sleep(seconds):
        sleep_calls.append(seconds)
        # Use sleep(0) to allow other coroutines to run without causing recursion
        # when asyncio.sleep is patched
        return None

    # Run worker briefly
    with patch("asyncio.sleep", side_effect=mock_sleep):
        task = asyncio.create_task(worker.start())
        await asyncio.sleep(0.2)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        await worker.stop()

    # Verify 15-second sleep after exception
    assert 15 in sleep_calls


# ===== Error Context Tests =====


@pytest.mark.asyncio
async def test_error_context_properly_added():
    """Test that error context is properly added and logged."""
    from unittest.mock import patch

    consumer = MockConsumer()
    producer = MockProducer()

    class TestWorker(BaseWorker[TestMessage]):
        def __init__(self, consumer, producer):
            super().__init__(consumer, producer)
            self.last_context: dict = {}

        async def on_message(self, message: TestMessage) -> bool:
            return True

        def _log(self) -> None:
            """Capture last context for testing."""
            context = self._get_context()
            if context:  # Only capture non-empty contexts
                self.last_context = context
            super()._log()

    worker = TestWorker(consumer, producer)

    messages = [TestMessage(id="1", data="test1")]

    # Mock consumer to return messages with error
    consume_count = [0]

    async def mock_consume(*args, **kwargs):
        if consume_count[0] < 1:
            consume_count[0] += 1
            return messages, ["Consumer validation error"]
        return [], []

    worker._consumer.consume_many = mock_consume

    # Mock sleep to avoid delay
    sleep_calls = []
    original_sleep = asyncio.sleep

    async def mock_sleep(seconds):
        sleep_calls.append(seconds)
        # Test delays (<5) actually sleep, worker delays (>=5) yield briefly
        if seconds < 5:
            await original_sleep(0.01)
        else:
            # Worker delays - very brief yield to allow other tasks to run
            await original_sleep(0)

    # Run worker briefly
    with patch("asyncio.sleep", side_effect=mock_sleep):
        task = asyncio.create_task(worker.start())
        await asyncio.sleep(0.2)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        await worker.stop()

    # Verify error context was added
    context = worker.last_context
    assert "error" in context
    assert "consumer" in context["error"]
    assert "validation error" in context["error"]["consumer"]


@pytest.mark.asyncio
async def test_processing_error_context_added():
    """Test that processing error context is properly added."""
    from unittest.mock import patch

    consumer = MockConsumer()
    producer = MockProducer()

    class TestWorker(BaseWorker[TestMessage]):
        def __init__(self, consumer, producer):
            super().__init__(consumer, producer)
            self.last_context: dict = {}

        async def on_message(self, message: TestMessage) -> bool:
            if message.id == "2":
                return False  # Fail this message
            return True

        def _log(self) -> None:
            """Capture last context for testing."""
            context = self._get_context()
            if context:  # Only capture non-empty contexts
                self.last_context = context
            super()._log()

    worker = TestWorker(consumer, producer)

    messages = [
        TestMessage(id="1", data="test1"),
        TestMessage(id="2", data="test2"),
    ]

    # Mock consumer to return messages then empty
    consume_count = [0]

    async def mock_consume(*args, **kwargs):
        if consume_count[0] < 1:
            consume_count[0] += 1
            return messages, []
        return [], []

    worker._consumer.consume_many = mock_consume

    # Mock sleep to avoid delay
    sleep_calls = []
    original_sleep = asyncio.sleep

    async def mock_sleep(seconds):
        sleep_calls.append(seconds)
        # Test delays (<5) actually sleep, worker delays (>=5) yield briefly
        if seconds < 5:
            await original_sleep(0.01)
        else:
            # Worker delays - very brief yield to allow other tasks to run
            await original_sleep(0)

    # Run worker briefly
    with patch("asyncio.sleep", side_effect=mock_sleep):
        task = asyncio.create_task(worker.start())
        await asyncio.sleep(0.2)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        await worker.stop()

    # Verify processing error context was added
    context = worker.last_context
    assert "error" in context
    assert "_processing" in context["error"]


@pytest.mark.asyncio
async def test_run_error_context_added():
    """Test that _run error context is properly added on exception."""
    from unittest.mock import patch

    consumer = MockConsumer()
    producer = MockProducer()

    class TestWorker(BaseWorker[TestMessage]):
        def __init__(self, consumer, producer):
            super().__init__(consumer, producer)
            self.last_context: dict = {}

        async def on_message(self, message: TestMessage) -> bool:
            return True

        def _log(self) -> None:
            """Capture last context for testing."""
            context = self._get_context()
            if context:  # Only capture non-empty contexts
                self.last_context = context
            super()._log()

    worker = TestWorker(consumer, producer)

    # Make consumer raise exception
    async def failing_consume(*args, **kwargs):
        raise RuntimeError("Runtime error occurred")

    worker._consumer.consume_many = failing_consume

    # Mock sleep to avoid delay
    sleep_calls = []
    original_sleep = asyncio.sleep

    async def mock_sleep(seconds):
        sleep_calls.append(seconds)
        # Test delays (<5) actually sleep, worker delays (>=5) yield briefly
        if seconds < 5:
            await original_sleep(0.01)
        else:
            # Worker delays - very brief yield to allow other tasks to run
            await original_sleep(0)

    # Run worker briefly
    with patch("asyncio.sleep", side_effect=mock_sleep):
        task = asyncio.create_task(worker.start())
        await asyncio.sleep(0.2)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        await worker.stop()

    # Verify _run error context was added
    context = worker.last_context
    assert "error" in context
    assert "_run" in context["error"]
    assert "Runtime error" in context["error"]["_run"]


# ===== Batch Size Edge Cases Tests =====


@pytest.mark.asyncio
async def test_batch_size_greater_than_max_messages():
    """Test batch_size > max_messages scenario."""
    consumer = MockConsumer()
    producer = MockProducer()

    class TestWorker(BaseWorker[TestMessage]):
        def __init__(self, consumer, producer):
            super().__init__(
                consumer,
                producer,
                batch_processing=True,
                batch_size=2000,  # batch_size > max_messages
                max_messages=1000,
            )
            self.processed_batches: list[list[TestMessage]] = []

        async def on_message_batch(self, messages: list[TestMessage]) -> bool:
            self.processed_batches.append(messages.copy())
            return True

    worker = TestWorker(consumer, producer)

    # Create messages
    messages = [TestMessage(id=str(i), data=f"test{i}") for i in range(500)]

    # Mock consumer to return messages then empty
    consume_count = [0]

    async def mock_consume(*args, **kwargs):
        if consume_count[0] < 1:
            consume_count[0] += 1
            return messages, None
        return [], None

    worker._consumer.consume_many = mock_consume

    # Run worker briefly
    task = asyncio.create_task(worker.start())
    await asyncio.sleep(0.2)
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass

    await worker.stop()

    # Worker should still process the batch correctly
    assert len(worker.processed_batches) == 1
    assert len(worker.processed_batches[0]) == 500


# ===== Context Management Tests =====


@pytest.mark.asyncio
async def test_context_set_get_reset():
    """Test _set_context, _get_context, and _reset_context."""
    consumer = MockConsumer()
    producer = MockProducer()

    worker = BaseWorker[TestMessage](consumer, producer)

    # Set initial context
    token = worker._set_context({"key1": "value1"})

    # Get context
    context = worker._get_context()
    assert context == {"key1": "value1"}

    # Add to context
    worker._add_context({"key2": "value2"})
    context = worker._get_context()
    assert context == {"key1": "value1", "key2": "value2"}

    # Reset context - this resets to state BEFORE the set() call (which was empty {})
    worker._reset_context(token)
    context = worker._get_context()
    assert context == {}


@pytest.mark.asyncio
async def test_context_nested_merge():
    """Test that _add_context properly merges nested dictionaries."""
    consumer = MockConsumer()
    producer = MockProducer()

    worker = BaseWorker[TestMessage](consumer, producer)

    # Set initial context with nested dict
    worker._set_context({"error": {"consumer": "error1"}})

    # Add nested context
    worker._add_context({"error": {"producer": "error2"}})
    context = worker._get_context()

    # Verify nested merge
    assert context["error"]["consumer"] == "error1"
    assert context["error"]["producer"] == "error2"


@pytest.mark.asyncio
async def test_context_multiple_adds():
    """Test multiple _add_context calls accumulate properly."""
    consumer = MockConsumer()
    producer = MockProducer()

    worker = BaseWorker[TestMessage](consumer, producer)

    # Set initial context
    token = worker._set_context({})

    # Add multiple contexts
    worker._add_context({"key1": "value1"})
    worker._add_context({"key2": "value2"})
    worker._add_context({"key3": "value3"})
    context = worker._get_context()

    # Verify all keys are present
    assert context == {"key1": "value1", "key2": "value2", "key3": "value3"}

    # Reset to original
    worker._reset_context(token)
    context = worker._get_context()
    assert context == {}


# ===== Logging Behavior Tests =====


@pytest.mark.asyncio
async def test_error_logged_as_error_level():
    """Test that messages with errors are logged at error level."""
    consumer = MockConsumer()
    producer = MockProducer()

    class TestWorker(BaseWorker[TestMessage]):
        def __init__(self, consumer, producer):
            super().__init__(consumer, producer)
            self.log_calls = []

        async def on_message(self, message: TestMessage) -> bool:
            return True

        def _log(self):
            """Override to capture log calls."""
            context = self._get_context()
            if "error" in context:
                self.log_calls.append(("error", context))
                self._logger.error(context)
            elif self._wide_event.sample():
                self.log_calls.append(("info", context))
                self._logger.info(context)

    worker = TestWorker(consumer, producer)

    messages = [TestMessage(id="1", data="test1")]

    # Mock consumer to return messages with error
    consume_count = [0]

    async def mock_consume(*args, **kwargs):
        if consume_count[0] < 1:
            consume_count[0] += 1
            return messages, "Consumer error"
        return [], None

    worker._consumer.consume_many = mock_consume

    # Mock sleep to avoid delay
    async def mock_sleep(seconds):
        # Cap sleeps to tiny amounts to allow worker to run quickly
        if seconds >= 15:
            await asyncio.sleep(0.001)
        elif seconds >= 60:
            await asyncio.sleep(0.001)
        else:
            await asyncio.sleep(0.0001)

    worker._sleep = mock_sleep

    # Run worker briefly
    task = asyncio.create_task(worker.start())
    await asyncio.sleep(0.2)
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass

    await worker.stop()

    # Verify error was logged at error level
    assert len(worker.log_calls) > 0


@pytest.mark.asyncio
async def test_success_logged_as_info_level():
    """Test that messages without errors are logged at info level."""
    consumer = MockConsumer()
    producer = MockProducer()

    class TestWorker(BaseWorker[TestMessage]):
        def __init__(self, consumer, producer):
            super().__init__(consumer, producer, sample_ratio=1.0)
            self.log_calls = []

        async def on_message(self, message: TestMessage) -> bool:
            return True

        def _log(self):
            """Override to capture log calls."""
            context = self._get_context()
            if "error" in context:
                self.log_calls.append(("error", context))
                self._logger.error(context)
            elif self._wide_event.sample():
                self.log_calls.append(("info", context))
                self._logger.info(context)

    worker = TestWorker(consumer, producer)

    messages = [TestMessage(id="1", data="test1")]

    # Mock consumer to return messages without error
    consume_count = [0]

    async def mock_consume(*args, **kwargs):
        if consume_count[0] < 1:
            consume_count[0] += 1
            return messages, None
        return [], None

    worker._consumer.consume_many = mock_consume

    # Mock sleep to avoid delay
    async def mock_sleep(seconds):
        # Cap sleeps to tiny amounts to allow worker to run quickly
        if seconds >= 15:
            await asyncio.sleep(0.001)
        elif seconds >= 60:
            await asyncio.sleep(0.001)
        else:
            await asyncio.sleep(0.0001)

    worker._sleep = mock_sleep

    # Run worker briefly
    task = asyncio.create_task(worker.start())
    await asyncio.sleep(0.2)
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass

    await worker.stop()

    # Verify success was logged at info level
    assert len(worker.log_calls) > 0


# ===== Multiple Batches Tests =====


@pytest.mark.asyncio
async def test_multiple_batches_processing():
    """Test processing multiple batches (loop continuation)."""
    from unittest.mock import patch

    consumer = MockConsumer()
    producer = MockProducer()

    class TestWorker(BaseWorker[TestMessage]):
        def __init__(self, consumer, producer):
            super().__init__(consumer, producer)
            self.processed_messages: list[TestMessage] = []

        async def on_message(self, message: TestMessage) -> bool:
            self.processed_messages.append(message)
            return True

    worker = TestWorker(consumer, producer)

    # Create multiple batches
    batch1 = [TestMessage(id="1", data="test1"), TestMessage(id="2", data="test2")]
    batch2 = [TestMessage(id="3", data="test3"), TestMessage(id="4", data="test4")]

    # Mock consumer to return multiple batches
    consume_count = [0]

    async def mock_consume(*args, **kwargs):
        consume_count[0] += 1
        if consume_count[0] == 1:
            return batch1, []
        elif consume_count[0] == 2:
            return batch2, []
        return [], []

    worker._consumer.consume_many = mock_consume

    # Mock sleep to speed up test
    async def mock_sleep(seconds):
        # Use sleep(0) to allow other coroutines to run without causing recursion
        # when asyncio.sleep is patched
        return None

    # Run worker briefly to process both batches
    with patch("asyncio.sleep", side_effect=mock_sleep):
        task = asyncio.create_task(worker.start())
        await asyncio.sleep(0.2)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        await worker.stop()

    # Verify all messages from both batches were processed
    assert len(worker.processed_messages) == 4
    assert worker.processed_messages[0].id == "1"
    assert worker.processed_messages[1].id == "2"
    assert worker.processed_messages[2].id == "3"
    assert worker.processed_messages[3].id == "4"


@pytest.mark.asyncio
async def test_batch_continuation_after_empty_batch():
    """Test that worker continues after empty batch."""
    from unittest.mock import patch

    consumer = MockConsumer()
    producer = MockProducer()

    class TestWorker(BaseWorker[TestMessage]):
        def __init__(self, consumer, producer):
            super().__init__(consumer, producer)
            self.processed_messages: list[TestMessage] = []

        async def on_message(self, message: TestMessage) -> bool:
            self.processed_messages.append(message)
            return True

    worker = TestWorker(consumer, producer)

    # Create batches with empty batch in between
    batch1 = [TestMessage(id="1", data="test1")]
    batch2 = [TestMessage(id="2", data="test2")]

    # Mock consumer to return batches with empty in between
    consume_count = [0]

    async def mock_consume(*args, **kwargs):
        consume_count[0] += 1
        if consume_count[0] == 1:
            return batch1, None
        elif consume_count[0] == 2:
            return [], None  # Empty batch
        elif consume_count[0] == 3:
            return batch2, None
        return [], None

    worker._consumer.consume_many = mock_consume

    # Mock sleep to avoid delay
    sleep_calls = []
    original_sleep = asyncio.sleep

    async def mock_sleep(seconds):
        sleep_calls.append(seconds)
        # Test delays (<5) actually sleep, worker delays (>=5) yield briefly
        if seconds < 5:
            await original_sleep(0.01)
        else:
            # Worker delays - very brief yield to allow other tasks to run
            await original_sleep(0)

    # Run worker briefly
    with patch("asyncio.sleep", side_effect=mock_sleep):
        task = asyncio.create_task(worker.start())
        await asyncio.sleep(0.2)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        await worker.stop()

    # Verify worker continued after empty batch
    assert len(worker.processed_messages) == 2
    assert worker.processed_messages[0].id == "1"
    assert worker.processed_messages[1].id == "2"


# ===== Start/Stop Order Tests =====


@pytest.mark.asyncio
async def test_consumer_starts_before_producer():
    """Test that consumer starts before producer."""
    consumer = MockConsumer()
    producer = MockProducer()

    class TestWorker(BaseWorker[TestMessage]):
        async def on_message(self, message: TestMessage) -> bool:
            return True

    worker = TestWorker(consumer, producer)
    worker._consumer.consume_many = AsyncMock(return_value=([], None))

    # Start worker
    start_task = asyncio.create_task(worker.start())
    await asyncio.sleep(0.1)

    # Verify consumer started first
    assert consumer._started is True
    assert producer._started is True
    assert consumer._start_count == 1
    assert producer._start_count == 1

    # Stop worker
    start_task.cancel()
    try:
        await start_task
    except asyncio.CancelledError:
        pass

    await worker.stop()


@pytest.mark.asyncio
async def test_consumer_stops_before_producer():
    """Test that consumer stops before producer."""
    consumer = MockConsumer()
    producer = MockProducer()

    class TestWorker(BaseWorker[TestMessage]):
        async def on_message(self, message: TestMessage) -> bool:
            return True

    worker = TestWorker(consumer, producer)
    worker._consumer.consume_many = AsyncMock(return_value=([], None))

    # Start worker
    start_task = asyncio.create_task(worker.start())
    await asyncio.sleep(0.1)

    # Stop worker
    start_task.cancel()
    try:
        await start_task
    except asyncio.CancelledError:
        pass

    await worker.stop()

    # Verify both stopped
    assert consumer._stopped is True
    assert producer._stopped is True


@pytest.mark.asyncio
async def test_start_stop_count_increments():
    """Test that start/stop counts increment correctly."""
    consumer = MockConsumer()
    producer = MockProducer()

    class TestWorker(BaseWorker[TestMessage]):
        async def on_message(self, message: TestMessage) -> bool:
            return True

    worker = TestWorker(consumer, producer)
    worker._consumer.consume_many = AsyncMock(return_value=([], None))

    # First start/stop cycle
    start_task = asyncio.create_task(worker.start())
    await asyncio.sleep(0.1)
    start_task.cancel()
    try:
        await start_task
    except asyncio.CancelledError:
        pass
    await worker.stop()

    # Verify counts
    assert consumer._start_count == 1
    assert producer._start_count == 1
    assert consumer._stop_count == 1
    assert producer._stop_count == 1


# ===== WideEventLogger Integration Tests =====


@pytest.mark.asyncio
async def test_wide_event_sample_ratio_used():
    """Test that WideEventLogger sample_ratio is properly used."""
    consumer = MockConsumer()
    producer = MockProducer()

    class TestWorker(BaseWorker[TestMessage]):
        async def on_message(self, message: TestMessage) -> bool:
            return True

    # Create worker with custom sample_ratio
    worker = TestWorker(consumer, producer, sample_ratio=0.5)

    # Verify wide_event has correct sample_ratio
    assert worker._wide_event.sample_ratio == 0.5


@pytest.mark.asyncio
async def test_wide_event_integration_with_worker():
    """Test that WideEventLogger integrates correctly with worker context."""
    from unittest.mock import patch

    consumer = MockConsumer()
    producer = MockProducer()

    class TestWorker(BaseWorker[TestMessage]):
        def __init__(self, consumer, producer):
            super().__init__(consumer, producer)
            self.processed_messages: list[TestMessage] = []
            self.last_context: dict = {}

        async def on_message(self, message: TestMessage) -> bool:
            self.processed_messages.append(message)
            return True

        def _log(self) -> None:
            """Capture last context for testing."""
            context = self._get_context()
            if context:  # Only capture non-empty contexts
                self.last_context = context
            super()._log()

    worker = TestWorker(consumer, producer)

    messages = [TestMessage(id="1", data="test1")]

    # Mock consumer to return messages then empty
    consume_count = [0]

    async def mock_consume(*args, **kwargs):
        if consume_count[0] < 1:
            consume_count[0] += 1
            return messages, None
        return [], None

    worker._consumer.consume_many = mock_consume

    # Mock sleep to avoid delay
    sleep_calls = []
    original_sleep = asyncio.sleep

    async def mock_sleep(seconds):
        sleep_calls.append(seconds)
        # Test delays (<5) actually sleep, worker delays (>=5) yield briefly
        if seconds < 5:
            await original_sleep(0.01)
        else:
            # Worker delays - very brief yield to allow other tasks to run
            await original_sleep(0)

    # Run worker briefly
    with patch("asyncio.sleep", side_effect=mock_sleep):
        task = asyncio.create_task(worker.start())
        await asyncio.sleep(0.2)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        await worker.stop()

    # Verify wide_event was used (context was set)
    context = worker.last_context
    assert "_run" in context


@pytest.mark.asyncio
async def test_wide_event_context_isolation_between_iterations():
    """Test that WideEventLogger context is isolated between loop iterations."""
    from unittest.mock import patch

    consumer = MockConsumer()
    producer = MockProducer()

    class TestWorker(BaseWorker[TestMessage]):
        def __init__(self, consumer, producer):
            super().__init__(consumer, producer)
            self.contexts = []

        async def on_message(self, message: TestMessage) -> bool:
            return True

        def _log(self):
            """Override to capture contexts."""
            context = self._get_context()
            self.contexts.append(context.copy())
            super()._log()

    worker = TestWorker(consumer, producer)

    # Create different messages for different iterations
    messages1 = [TestMessage(id="1", data="test1")]
    messages2 = [TestMessage(id="2", data="test2")]

    # Mock consumer to return different batches
    consume_count = [0]

    async def mock_consume(*args, **kwargs):
        consume_count[0] += 1
        if consume_count[0] == 1:
            return messages1, None
        elif consume_count[0] == 2:
            return messages2, None
        return [], None

    worker._consumer.consume_many = mock_consume

    # Mock sleep to avoid delay
    sleep_calls = []
    original_sleep = asyncio.sleep

    async def mock_sleep(seconds):
        sleep_calls.append(seconds)
        # Test delays (<5) actually sleep, worker delays (>=5) yield briefly
        if seconds < 5:
            await original_sleep(0.01)
        else:
            # Worker delays - very brief yield to allow other tasks to run
            await original_sleep(0)

    # Run worker briefly
    with patch("asyncio.sleep", side_effect=mock_sleep):
        task = asyncio.create_task(worker.start())
        await asyncio.sleep(0.2)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        await worker.stop()

    # Verify multiple contexts were captured (multiple iterations)
    assert len(worker.contexts) >= 2
