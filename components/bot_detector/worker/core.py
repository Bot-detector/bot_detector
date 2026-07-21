import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Generic, Literal, Type, TypeVar

from bot_detector.event_queue.adapters.kafka import KafkaConfig
from bot_detector.event_queue.adapters.memory import InMemoryConfig
from bot_detector.event_queue.core import Queue
from bot_detector.event_queue.factory import QueueFactory
from bot_detector.worker.errors import WorkerError
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

logger = logging.getLogger(__name__)


class Worker(ABC, Generic[T]):
    """Abstract worker. Subclass and implement handle().

    Receives a batch of messages and does work (DB writes, Kafka produce, API calls).

    Requeue contract — handle() may return either a list or a WorkerError:
        - Return [] (or any empty list) to signal full success — the runner
          commits the batch offsets.
        - Return a non-empty subset to requeue only those messages — the runner
          re-publishes them and then commits the original batch offsets.
        - Return a WorkerError(ok_batch=..., error_batch=...) to signal a
          failure with partial progress: the runner re-publishes error_batch
          and commits the batch offsets; ok_batch is considered processed and
          is not requeued. This is the errors-as-values equivalent of raising.
        - Raise an exception to requeue the entire batch (with backoff). Use this
          for all-or-nothing workers or when the batch cannot be partially
          progressed.

    Returned messages must be valid instances of T; the runner does not validate
    them. Workers using partial requeue must be idempotent on re-delivery.
    """

    @abstractmethod
    async def handle(self, batch: list[T]) -> list[T] | WorkerError[T]:
        """Process a batch and return the messages to requeue (empty = success).

        May instead return a WorkerError carrying ok_batch/error_batch to
        signal that error_batch should be requeued while ok_batch is kept.
        """
        ...


class WorkerRunner(Generic[T]):
    """Owns the queue, runs the consume loop for a Worker.

    Creates queue via QueueFactory.
    Loop: get_many → handle → commit. Requeues the subset returned by handle
    (or the whole batch if handle raises). Graceful shutdown on CancelledError.
    """

    def __init__(
        self,
        config: KafkaConfig | InMemoryConfig,
        model: Type[T],
        worker: Worker[T],
        stop_event: asyncio.Event,
        batch_size: int = 1000,
    ) -> None:
        self._worker = worker
        self._batch_size = batch_size
        self._config = config
        self._model = model
        self._stop_event = stop_event
        self._queue: Queue[T] = self._create_queue()

    def _detect_backend(self) -> Literal["kafka", "memory"]:
        if isinstance(self._config, KafkaConfig):
            return "kafka"
        if isinstance(self._config, InMemoryConfig):
            return "memory"
        raise ValueError(f"Unknown config type: {type(self._config)}")

    def _create_queue(self) -> Queue[T]:
        result = QueueFactory.create_queue(
            model=self._model,
            queue_type="queue",
            backend_type=self._detect_backend(),
            config=self._config,
        )
        if isinstance(result, Exception):
            raise result
        if not isinstance(result, Queue):
            raise ValueError(
                f"Expected Queue, got {type(result).__name__}. "
                "WorkerRunner requires queue_type='queue' (consumer + producer)."
            )
        return result

    async def run(self) -> None:
        """Start queue, run consume loop. Graceful shutdown on CancelledError."""
        try:
            await self._queue.start()
            await self._consume()
        except asyncio.CancelledError:
            logger.info("WorkerRunner received shutdown signal.")
        finally:
            await self._queue.stop()

    async def _requeue(self, batch: list[T]) -> None:
        """Requeue batch and commit. Logs errors but does not raise."""
        requeue_err = await self._queue.put(batch)
        if isinstance(requeue_err, Exception):
            logger.error(f"Failed to requeue batch: {requeue_err}")
            return
        commit_err = await self._queue.commit()
        if isinstance(commit_err, Exception):
            logger.error(f"Failed to commit requeued batch: {commit_err}")

    async def _consume(self) -> None:
        """Main loop: get_many → handle → commit. Requeues what handle returns."""
        while not self._stop_event.is_set():
            batch: list[T] = []
            try:
                result = await self._queue.get_many(self._batch_size)
                if isinstance(result, Exception):
                    logger.error(f"Error consuming messages: {result}")
                    continue

                batch = result
                if not batch:
                    await asyncio.sleep(0.1)
                    continue

                logger.info(f"Consumed {len(batch)} messages")

                result = await self._worker.handle(batch)
                if isinstance(result, WorkerError):
                    if result.error_batch:
                        logger.error(
                            f"Worker returned error: {result}. "
                            f"ok={len(result.ok_batch)}, "
                            f"requeuing={len(result.error_batch)} "
                            f"of {len(batch)}"
                        )
                        await self._requeue(result.error_batch)
                        await asyncio.sleep(1)
                    else:
                        logger.warning(
                            f"Worker returned WorkerError with empty "
                            f"error_batch, committing: {result}"
                        )
                        commit_err = await self._queue.commit()
                        if isinstance(commit_err, Exception):
                            logger.error(f"Failed to commit batch: {commit_err}")
                elif result:
                    logger.info(f"Requeuing {len(result)} of {len(batch)} messages")
                    await self._requeue(result)
                else:
                    commit_err = await self._queue.commit()
                    if isinstance(commit_err, Exception):
                        logger.error(f"Failed to commit batch: {commit_err}")
            except asyncio.CancelledError:
                if batch:
                    await self._requeue(batch)
                raise
            except Exception as e:
                logger.error(f"Error processing batch: {e}", exc_info=True)
                if batch:
                    await self._requeue(batch)
                await asyncio.sleep(1)

        logger.info("WorkerRunner consume loop exiting.")
