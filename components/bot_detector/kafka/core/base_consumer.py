# base_consumer.py

import asyncio
import logging
from typing import (
    Callable,
    Generic,
    List,
    Optional,
    TypeVar,
)

import orjson
from aiokafka import AIOKafkaConsumer, TopicPartition
from pydantic import BaseModel, ValidationError

from .batcher import Batcher

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class BaseConsumer(Generic[T]):
    """
    Generic async Kafka consumer with Pydantic validation and batching.
    """

    def __init__(
        self,
        topic: str,
        group_id: str,
        bootstrap_servers: str,
        deserializer: Callable[[dict], T],
        enable_auto_commit: bool = True,
    ):
        self.topic = topic
        self.deserializer = deserializer
        self._consumer = AIOKafkaConsumer(
            topic,
            group_id=group_id,
            value_deserializer=lambda x: orjson.loads(x),
            auto_offset_reset="earliest",
            bootstrap_servers=bootstrap_servers,
            enable_auto_commit=enable_auto_commit,
        )

    # --------------------
    # Lifecycle
    # --------------------

    async def start(self):
        await self._consumer.start()
        return self._consumer

    async def stop(self):
        await self._consumer.stop()

    async def get_consumer(self):
        return self._consumer

    async def commit(self):
        await self._consumer.commit()

    # --------------------
    # Low-level consume primitives
    # --------------------

    async def consume_one(self) -> tuple[Optional[T], Optional[str]]:
        try:
            consumer_record = await self._consumer.getone()
        except Exception as e:
            return None, f"Kafka getone error: {e}"

        if not isinstance(consumer_record.value, dict):
            return None, "Message value is not a dict"

        try:
            return self.deserializer(consumer_record.value), None
        except ValidationError as ve:
            logger.warning(f"Validation error: {ve}")
            return None, f"Validation error: {ve}"

    async def consume_many(
        self, max_records: int, timeout_ms: int
    ) -> tuple[List[T], List[str]]:
        batcher = Batcher[T](batch_size=max_records, timeout_ms=timeout_ms)
        errors: List[str] = []

        while not batcher.check_flush():
            remaining_ms = int(batcher.time_left * 1000)
            if remaining_ms <= 0:
                break

            try:
                records = await self._consumer.getmany(
                    timeout_ms=remaining_ms,
                    max_records=max_records - batcher.size,
                )
            except Exception as e:
                errors.append(f"Kafka getmany error: {e}")
                break

            if not records:
                await asyncio.sleep(0.01)  # prevent busy-loop
                continue

            for consumer_records in records.values():
                for r in consumer_records:
                    if not isinstance(r.value, dict):
                        errors.append("Message value is not a dict")
                        continue
                    try:
                        batcher.append(self.deserializer(r.value), auto=False)
                    except ValidationError as ve:
                        errors.append(f"Validation error: {ve}")

        return batcher.flush(), errors

    # --------------------
    # Metrics
    # --------------------

    async def get_lag(self) -> int:
        total_lag = 0

        partitions = self._consumer.partitions_for_topic(self.topic)
        if partitions is None:
            return 0

        for partition in partitions:
            tp = TopicPartition(self.topic, partition)
            committed = await self._consumer.committed(tp) or 0
            end_offset = await self._consumer.end_offsets([tp])
            lag = end_offset[tp] - committed
            total_lag += lag

        return total_lag
