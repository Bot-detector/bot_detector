import asyncio
import logging
from typing import Any, Generic, TypeVar

from bot_detector.kafka import ConsumerInterface, ProducerInterface
from bot_detector.wide_event import EventLoggerInterface, WideEventLogger
from pydantic import BaseModel

from .interface import WorkerInterface

T = TypeVar("T", bound=BaseModel)


class BaseWorker(Generic[T], WorkerInterface[T]):
    """Generic worker with minimal boilerplate and integrated logging."""

    EMPTY_MESSAGE_SLEEP = 10
    PRODUCE_RETRY_DELAY = 5
    PRODUCE_MAX_RETRY = 3

    def __init__(
        self,
        consumer: ConsumerInterface[T],
        producer: ProducerInterface[T],
        max_messages: int = 10_000,
        max_interval_ms: int = 5_000,
        batch_processing: bool = False,
        wide_event: EventLoggerInterface = WideEventLogger(sample_ratio=0.1),
        logger_name: str | None = None,
    ) -> None:
        self._consumer = consumer
        self._producer = producer
        self._max_messages = max_messages
        self._max_interval_ms = max_interval_ms
        self._batch_processing = batch_processing
        self._wide_event = wide_event
        self._logger = logging.getLogger(logger_name or self.__class__.__name__)
        self._stop_event = asyncio.Event()

    async def on_message(self, message: T) -> bool:
        """Override with single message logic. Return True for success."""
        return True

    async def on_message_batch(self, messages: list[T]) -> bool:
        """Override with batch message logic. Return True if all succeed."""
        for msg in messages:
            if not await self.on_message(msg):
                return False
        return True

    async def start(self) -> None:
        await self._consumer.start()
        await self._producer.start()
        await self._run()

    async def stop(self) -> None:
        self._stop_event.set()
        await self._consumer.stop()
        await self._producer.stop()

    # ------------------------
    # Hooks
    # ------------------------
    async def _consume_error_hook(self, errors: list[str]):
        self._add_context({"error": {"consumer_errors": errors[:5]}})

    async def _empty_message_hook(self):
        self._add_context({"_run": {"status": "empty"}})
        await asyncio.sleep(self.EMPTY_MESSAGE_SLEEP)

    async def _failed_on_message_hook(self):
        self._add_context({"_run": {"status": "failed"}})

    async def _success_on_message_hook(self):
        self._add_context({"_run": {"status": "success"}})

    # ------------------------
    # Retry logic
    # ------------------------
    async def _produce_failed_messages(self, batch: list[T]) -> None:
        errors: list[str] = []

        for message in batch:
            retry_count = 0
            while retry_count < self.PRODUCE_MAX_RETRY:
                try:
                    await self._producer.produce_one(message=message)
                    break
                except Exception as e:
                    retry_count += 1
                    if retry_count >= self.PRODUCE_MAX_RETRY:
                        errors.append(str(e))
                        break
                    await asyncio.sleep(self.PRODUCE_RETRY_DELAY)

        if errors:
            self._add_context({"error": {"produce_failed_messages": errors[:5]}})

    # ------------------------
    # Core processing loops
    # ------------------------
    async def _run_one(self) -> list[T]:
        failed: list[T] = []
        message, consume_error = await self._consumer.consume_one()
        if consume_error:
            await self._consume_error_hook([consume_error])
        if message is None:
            await self._empty_message_hook()
        else:
            if await self.on_message(message):
                await self._success_on_message_hook()
            else:
                failed.append(message)
                await self._failed_on_message_hook()
        return failed

    async def _run_many(self) -> list[T]:
        failed_messages: list[T] = []
        batch, errors = await self._consumer.consume_many(
            max_records=self._max_messages, timeout_ms=self._max_interval_ms
        )

        if errors:
            await self._consume_error_hook(errors)

        if not batch:
            await self._empty_message_hook()
            return []

        self._add_context({"_run": {"batch_size": len(batch)}})

        if await self.on_message_batch(batch):
            await self._success_on_message_hook()
        else:
            failed_messages.extend(batch)
            await self._failed_on_message_hook()

        return failed_messages

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            token = self._set_context(data={})
            try:
                if self._batch_processing:
                    failed_messages = await self._run_many()
                else:
                    failed_messages = await self._run_one()
                await self._produce_failed_messages(failed_messages)
                await self._consumer.commit()
            except Exception as e:
                self._add_context({"error": {"_run_exception": str(e)}})
                await asyncio.sleep(15)
            finally:
                self._log()
                self._reset_context(token)

    # ------------------------
    # WideEvent logging
    # ------------------------
    def _set_context(self, data: dict) -> Any:
        return self._wide_event.set(data)

    def _add_context(self, data: dict) -> None:
        self._wide_event.add(data)

    def _get_context(self) -> dict:
        return self._wide_event.get()

    def _reset_context(self, token: Any) -> None:
        self._wide_event.reset(token)

    def _log(self) -> None:
        context = self._get_context()
        if "error" in context:
            self._logger.error(context)
        elif self._wide_event.sample():
            self._logger.info(context)
