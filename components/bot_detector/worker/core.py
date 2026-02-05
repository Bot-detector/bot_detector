import asyncio
import logging
from typing import Any, Generic, TypeVar

from bot_detector.event_queue.core import Queue, QueueProducer
from bot_detector.wide_event import EventLoggerInterface, WideEventLogger
from pydantic import BaseModel

from .interface import ConsumerWorkerInterface, ProducerWorkerInterface

T = TypeVar("T", bound=BaseModel)


class BaseWorker(Generic[T]):
    """Generic worker with minimal boilerplate and integrated logging."""

    EMPTY_MESSAGE_SLEEP = 10

    def __init__(
        self,
        wide_event: EventLoggerInterface = WideEventLogger(sample_ratio=0.1),
        logger_name: str | None = None,
    ) -> None:
        self._wide_event = wide_event
        self._logger = logging.getLogger(logger_name or self.__class__.__name__)
        self._stop_event = asyncio.Event()

    # ------------------------
    # Hooks
    # ------------------------
    async def _consume_error_hook(self, errors: list[Exception]):
        error_messages = [str(error) for error in errors[:5]]
        self._add_context({"error": {"consumer_errors": error_messages}})

    async def _empty_message_hook(self):
        self._add_context({"_run": {"status": "empty"}})
        await asyncio.sleep(self.EMPTY_MESSAGE_SLEEP)

    async def _failed_on_message_hook(self, error: Exception):
        self._add_context({"_run": {"status": "failed", "error": str(error)}})

    async def _success_on_message_hook(self):
        self._add_context({"_run": {"status": "success"}})

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


class ConsumerWorker(BaseWorker[T], ConsumerWorkerInterface[T]):
    """Worker that consumes messages from a queue and processes them."""

    MAX_MESSAGES = 10_000

    def __init__(
        self,
        queue: Queue[T],
        batch_processing: bool = False,
        wide_event: EventLoggerInterface = WideEventLogger(sample_ratio=0.1),
        logger_name: str | None = None,
    ) -> None:
        super().__init__(wide_event=wide_event, logger_name=logger_name)
        self._queue = queue
        self._batch_processing = batch_processing

    async def on_message(self, message: T) -> Exception | None:
        """Override with single message logic. Return Exception on failure."""
        return None

    async def on_message_batch(self, messages: list[T]) -> Exception | None:
        """Override with batch message logic. Return Exception on failure."""
        for msg in messages:
            error = await self.on_message(msg)
            if error:
                return error
        return None

    async def start(self) -> None:
        await self._queue.start()
        await self._run()

    async def stop(self) -> None:
        self._stop_event.set()
        await self._queue.stop()

    async def _produce_failed_messages(self, batch: list[T]) -> None:
        error = await self._queue.put(batch)
        if error:
            self._add_context({"error": {"produce_failed_messages": [str(error)]}})

    async def _run_one(self) -> list[T]:
        failed: list[T] = []
        result = await self._queue.get_one()
        if isinstance(result, Exception):
            await self._consume_error_hook([result])
            await self._empty_message_hook()
            return failed
        if result is None:
            await self._empty_message_hook()
            return failed
        message = result
        error = await self.on_message(message)
        if error is None:
            await self._success_on_message_hook()
        else:
            failed.append(message)
            await self._failed_on_message_hook(error)
        return failed

    async def _run_many(self) -> list[T]:
        failed_messages: list[T] = []
        result = await self._queue.get_many(self.MAX_MESSAGES)
        if isinstance(result, Exception):
            await self._consume_error_hook([result])
            await self._empty_message_hook()
            return failed_messages
        if not result:
            await self._empty_message_hook()
            return failed_messages
        batch = result
        self._add_context({"_run": {"batch_size": len(batch)}})
        error = await self.on_message_batch(batch)
        if error is None:
            await self._success_on_message_hook()
        else:
            failed_messages.extend(batch)
            await self._failed_on_message_hook(error)

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
                commit_error = await self._queue.commit()
                if commit_error:
                    await self._consume_error_hook([commit_error])
            except Exception as e:
                self._add_context({"error": {"_run_exception": str(e)}})
                await asyncio.sleep(15)
            finally:
                self._log()
                self._reset_context(token)


class ProducerWorker(BaseWorker[T], ProducerWorkerInterface[T]):
    """Worker that builds and produces messages to a queue."""

    def __init__(
        self,
        queue: QueueProducer[T] | Queue[T],
        wide_event: EventLoggerInterface = WideEventLogger(sample_ratio=0.1),
        logger_name: str | None = None,
    ) -> None:
        super().__init__(wide_event=wide_event, logger_name=logger_name)
        self._queue = queue

    async def build_messages(self) -> list[T] | Exception | None:
        """Override to return a batch of messages to produce."""
        return None

    async def start(self) -> None:
        await self._queue.start()
        await self._run()

    async def stop(self) -> None:
        self._stop_event.set()
        await self._queue.stop()

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            token = self._set_context(data={})
            try:
                result = await self.build_messages()
                if isinstance(result, Exception):
                    await self._failed_on_message_hook(result)
                    await self._empty_message_hook()
                    continue
                if not result:
                    await self._empty_message_hook()
                    continue
                error = await self._queue.put(result)
                if error:
                    self._add_context(
                        {"error": {"produce_failed_messages": [str(error)]}}
                    )
            except Exception as e:
                self._add_context({"error": {"_run_exception": str(e)}})
                await asyncio.sleep(15)
            finally:
                self._log()
                self._reset_context(token)
