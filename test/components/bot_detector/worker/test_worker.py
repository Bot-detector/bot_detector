import asyncio
from typing import Any, Optional
from unittest.mock import AsyncMock, Mock

import pytest
from bot_detector.worker import BaseWorker
from pydantic import BaseModel

"""
we need to test the Basewoker, the strategy is to create a Mock Consumer and Producer
that implement the ConsumerInterface and ProducerInterface respectively, but where we can
control the behavior of the methods with an additional method to add messages and an
internal parameter to hold these messages. We will also create a simple Message model,
TestMessage model, then we will create a TestWorker that inherits from BaseWorker
and implement the on_message and on_message_batch methods.

class ProducerInterface(Protocol, Generic[T]):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def get_producer(self) -> Any: ...
    async def produce_one(
        self,
        message: T,
        topic: Optional[str] = None,
        partition_key: Optional[bytes] = None,
        max_retries: int = 5,
    ): ...

class ConsumerInterface(Protocol, Generic[T]):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def get_consumer(self) -> Any: ...
    async def commit(self) -> None: ...
    async def consume_one(self) -> tuple[Optional[T], Optional[str]]: ...
    async def consume_many(
        self, max_records: int, timeout_ms: int
    ) -> tuple[list[T], list[str]]: ...
    async def get_lag(self) -> int: ...

class WorkerInterface(Protocol, Generic[T]):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def on_message(self, message: T) -> bool: ...
    async def on_message_batch(self, messages: list[T]) -> bool: ...

class BaseWorker(Generic[T], WorkerInterface[T]):
    Init Args:
        consumer: ConsumerInterface: Kafka consumer for this worker
        producer: ProducerInterface: Kafka producer for retry messages
        max_messages: Max messages per batch from Kafka (default: 10_000)
        max_interval_ms: Max wait interval in ms (default: 5_000)
        batch_processing: Enable batch message processing (default: False)
        wide_event: WideEventLogger for structured logging (default: WideEventLogger with 0.1 sample ratio)
        logger_name: Optional logger name (default: class name)
"""


class TestMessage(BaseModel):
    id: str
    data: str


async def test_worker_process_message():
    """
    we need to test the Basewoker
    """
