import asyncio
import logging
from typing import Any, Generic, TypeVar

from bot_detector.kafka import ConsumerInterface, ProducerInterface
from bot_detector.wide_event import WideEventLogger
from pydantic import BaseModel

from .interface import WorkerInterface

T = TypeVar("T", bound=BaseModel)


class BaseWorker(Generic[T], WorkerInterface[T]):
    """Generic worker with minimal boilerplate and integrated logging.

    Usage:
        class CustomWorker(Worker[MessageStruct]):
            async def on_message(self, message: MessageStruct) -> bool:
                # Your business logic here
                return True  # or False to retry
            async def on_message_batch(self, messages: list[MessageStruct]) -> bool:
                # Your batch business logic here
                return True  # or False to retry

        consumer = YourKafkaConsumer(...)
        producer = YourKafkaProducer(...)

        # Single message mode
        worker = Worker[MessageStruct](consumer, producer)
        await worker.start()

        # Batch mode
        worker = Worker[MessageStruct](consumer, producer, batch_processing=True, batch_size=100)
        await worker.start()

        # With custom sample ratio
        worker = Worker[MessageStruct](consumer, producer, sample_ratio=0.02)
        await worker.start()
    """

    def __init__(
        self,
        consumer: ConsumerInterface[T],
        producer: ProducerInterface[T],
        max_messages: int = 10_000,
        max_interval_ms: int = 5_000,
        batch_processing: bool = False,
        batch_size: int = 1,
        sample_ratio: float = 0.01,
    ) -> None:
        """Initialize worker.

        Args:
            consumer: Kafka consumer for this worker
            producer: Kafka producer for retry messages
            max_messages: Max messages per batch from Kafka (default: 10_000)
            max_interval_ms: Max wait interval in ms (default: 5_000)
            batch_processing: Enable batch message processing (default: False)
            batch_size: Number of messages per batch when batch_processing=True (default: 1)
            sample_ratio: Sample ratio for successful messages (default: 0.01 = 1%)
        """
        self._consumer = consumer
        self._producer = producer
        self._max_messages = max_messages
        self._max_interval_ms = max_interval_ms
        self._batch_processing = batch_processing
        self._batch_size = batch_size
        self._sample_ratio = sample_ratio
        self._wide_event = WideEventLogger(sample_ratio=sample_ratio)
        self._logger = logging.getLogger(self.__class__.__name__)

    async def on_message(self, message: T) -> bool:
        """Process a single message.

        Override with your business logic.
        Returns True for success, False to retry.
        """
        return True

    async def on_message_batch(self, messages: list[T]) -> bool:
        """Process a batch of messages.

        Optional - only implement when batch_processing=True.
        Returns True if all successful, False to retry.
        """
        for message in messages:
            if not await self.on_message(message):
                return False
        return True

    async def start(self) -> None:
        await self._consumer.start()
        await self._producer.start()
        await self._run()

    async def stop(self) -> None:
        await self._consumer.stop()
        await self._producer.stop()

    async def _run(self) -> None:
        """Main worker loop with error-based sampling.

        Uses try/finally to manage WideEventLogger context:
        - If error key exists → always log (regardless of sample_ratio)
        - If no error key → sample based on sample_ratio
        """
        while True:
            # Set initial context (error: None by default)
            token = self._set_context(data={})

            try:
                batch, errors = await self._consumer.consume_many(
                    max_records=self._max_messages,
                    timeout_ms=self._max_interval_ms,
                )

                if errors:
                    self._add_context({"error": {"consumer": str(errors)}})

                if not batch:
                    await asyncio.sleep(15)
                    continue

                self._add_context({"_run": {"batch": f"received {len(batch)}"}})

                failed_messages = []
                if self._batch_processing:
                    if not await self.on_message_batch(batch):
                        self._add_context({"error": {"_processing": "Batch failed"}})
                        failed_messages.extend(batch)
                else:
                    for message in batch:
                        if not await self.on_message(message):
                            self._add_context(
                                {"error": {"_processing": "message failed"}}
                            )
                            failed_messages.append(message)

                await self._retry_failed_messages(failed_messages)
                await self._consumer.commit()

                if len(batch) < 1000:
                    await asyncio.sleep(60)

            except Exception as e:
                self._add_context({"error": {"_run": str(e)}})
                await asyncio.sleep(15)
            finally:
                # Log based on error-based sampling strategy
                self._log()
                # Reset context in finally to ensure cleanup
                self._reset_context(token)

    async def _retry_failed_messages(self, batch: list[T]) -> None:
        """Retry failed messages from batch."""
        for message in batch:
            try:
                await self._producer.produce_one(message=message)
            except Exception as e:
                self._add_context({"error": {"retry_error": str(e)}})
        await asyncio.sleep(15)

    def _set_context(self, data: dict) -> Any:
        """Set log context for structured logging."""
        return self._wide_event.set(data)

    def _add_context(self, data: dict) -> None:
        """Add to log context for structured logging."""
        self._wide_event.add(data)

    def _get_context(self) -> dict:
        """Get current log context."""
        return self._wide_event.get()

    def _reset_context(self, token: Any) -> None:
        """Reset log context."""
        self._wide_event.reset(token)

    def _log(self) -> None:
        """Log context with error-based sampling.

        Error-based sampling strategy:
        - If 'error' key exists → always log (regardless of sample_ratio)
        - If no 'error' key → sample based on wide_event.sample_ratio
        """
        context = self._get_context()
        if "error" in context:
            # Errors always logged (high priority)
            self._logger.error(context)
        elif self._wide_event.sample():
            # Successful messages sampled (low priority)
            self._logger.info(context)
