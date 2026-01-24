# base_producer.py

import asyncio
import logging
from typing import Generic, Optional, TypeVar

import orjson
from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaTimeoutError
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class BaseProducer(Generic[T]):
    """
    Generic async Kafka producer with Pydantic serialization and concurrency control.
    """

    def __init__(
        self,
        bootstrap_servers: str,
        topic: Optional[str] = None,
        max_async_actions: int = 10,
    ):
        """
        Args:
            bootstrap_servers: Kafka bootstrap servers.
            serializer: Function to convert Pydantic model -> dict.
            topic: Default topic to send messages to (can be overridden per message).
            max_async_actions: Max concurrent produce calls.
        """
        self.topic = topic
        self._producer = AIOKafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: orjson.dumps(v),
            acks="all",
        )
        self.semaphore = asyncio.Semaphore(value=max_async_actions)

    # --------------------
    # Lifecycle
    # --------------------

    async def start(self):
        await self._producer.start()
        return self._producer

    async def stop(self):
        await self._producer.stop()

    async def get_producer(self):
        return self._producer

    # --------------------
    # Produce API
    # --------------------

    async def produce_one(
        self,
        message: T,
        topic: str | None = None,
        partition_key: bytes | None = None,
        max_retries: int = 5,
    ):
        """
        Produce a single message with retries on KafkaTimeoutError.

        Args:
            message: Pydantic model instance
            topic: Optional topic override
            partition_key: Optional Kafka key
            max_retries: Max exponential backoff retries
        """
        _topic = topic or self.topic
        if _topic is None:
            raise ValueError("Topic must be specified")

        try:
            payload = message.model_dump()
        except ValidationError as ve:
            logger.warning(f"Failed to serialize message: {ve}")
            return

        retries = 0
        MAX_BACKOFF = 60
        while True:
            async with self.semaphore:
                try:
                    await self._producer.send(
                        topic=_topic,
                        value=payload,
                        key=partition_key,
                    )
                    break
                except KafkaTimeoutError as e:
                    retries += 1
                    if retries > max_retries:
                        logger.error(
                            f"Max retries reached producing message to {_topic}: {e}"
                        )
                        break
                    backoff = min(2**retries, MAX_BACKOFF)
                    logger.warning(
                        f"KafkaTimeoutError sending to {_topic} (retry {retries}, backoff {backoff}s)"
                    )
                    await asyncio.sleep(backoff)
