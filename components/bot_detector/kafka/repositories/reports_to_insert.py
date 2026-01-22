import asyncio
import logging
import time

import orjson
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, TopicPartition
from aiokafka.errors import KafkaTimeoutError
from bot_detector.kafka.interface import (
    ConsumerInterface,
    ProducerInterface,
)
from bot_detector.structs import ReportsToInsertStruct

logger = logging.getLogger(__name__)


class RepoReportsToInsertConsumer(ConsumerInterface):
    def __init__(
        self,
        group_id: str,
        bootstrap_servers: str,
        enable_auto_commit: bool = True,
    ):
        self.topic = "reports.to_insert"
        self.consumer = AIOKafkaConsumer(
            self.topic,
            group_id=group_id,
            value_deserializer=lambda x: orjson.loads(x),
            auto_offset_reset="earliest",
            bootstrap_servers=bootstrap_servers,
            enable_auto_commit=enable_auto_commit,
        )

    async def start(self):
        await self.consumer.start()
        return self.consumer

    async def stop(self):
        await self.consumer.stop()

    async def get_consumer(self):
        return self.consumer

    def _validate_value(self, value) -> tuple[dict | None, str | None]:
        if not isinstance(value, dict):
            return None, "Message value is not a dict"
        if "metadata" not in value:
            return None, "Missing required field 'metadata' in message value"
        if "report" not in value:
            return None, "Missing required field 'report' in message value"
        return value, None

    async def consume_one(self) -> ReportsToInsertStruct:
        msg = await self.consumer.getone()
        value, error = self._validate_value(value=msg.value)

        if error:
            raise ValueError(f"Invalid message value: {error}")

        if not value:
            raise ValueError("Message value is None")

        report = ReportsToInsertStruct(
            metadata=value["metadata"],
            report=value["report"],
        )
        return report

    async def buffer_records(self, max_records: int, timeout_ms: int) -> list:
        """
        Collect up to `max_records` from Kafka within `timeout_ms`.

        Unlike `getmany()`, which returns early when any data is available,
        this method accumulates records in a loop to form a larger batch,
        or until the timeout is reached.

        Args:
            max_records (int): Max number of records to collect.
            timeout_ms (int): Max time to wait (in milliseconds).

        Returns:
            list: Buffered records (may be fewer than `max_records`).
        """
        buffer = []
        start = time.time()

        while len(buffer) < max_records:
            time_left = timeout_ms / 1000 - (time.time() - start)

            if time_left <= 0:
                break

            records = await self.consumer.getmany(
                timeout_ms=int(time_left * 1000),
                max_records=max_records - len(buffer),
            )
            buffer.extend([msg.value for msgs in records.values() for msg in msgs])

        return buffer

    async def consume_many(
        self,
        max_messages: int = 10_000,
        timeout_ms: int = 1_000,
    ) -> tuple[list[ReportsToInsertStruct], list[str]]:
        msg_values = await self.buffer_records(
            max_records=max_messages,
            timeout_ms=timeout_ms,
        )

        reports, errors = [], []

        for value in msg_values:
            value, error = self._validate_value(value)

            if error:
                errors.append(error)
                continue

            if not value:
                errors.append("Message value is None")
                continue

            report = ReportsToInsertStruct(
                metadata=value["metadata"],
                report=value["report"],
            )
            reports.append(report)
        return reports, errors

    async def get_lag(self) -> int:
        total_lag = 0

        # Get the list of partitions for the topic
        partitions = self.consumer.partitions_for_topic(self.topic)

        if partitions is None:
            logger.warning("partitions is none")
            return 0

        for partition in partitions:
            tp = TopicPartition(self.topic, partition)

            # Get the last offset committed by the consumer
            committed = await self.consumer.committed(tp)

            # Get the latest offset in the topic
            end_offset = await self.consumer.end_offsets([tp])

            # Calculate the lag for this partition
            lag = end_offset[tp] - committed

            # Add the lag for this partition to the total lag
            total_lag += lag

        return total_lag

    async def commit(self):
        await self.consumer.commit()


class RepoReportsToInsertProducer(ProducerInterface):
    def __init__(self, bootstrap_servers: str, max_async_calls: int):
        self.producer = AIOKafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: orjson.dumps(v),
            acks="all",
        )
        self.topic = "reports.to_insert"
        self.semaphore = asyncio.Semaphore(value=max_async_calls)

    async def start(self):
        await self.producer.start()
        return self

    async def stop(self):
        await self.producer.stop()

    async def get_producer(self):
        return self.producer

    async def produce_one(self, report: ReportsToInsertStruct):
        if not isinstance(report, ReportsToInsertStruct):
            raise Exception()

        retries = 0
        MAX_BACKOFF = 60
        while True:
            async with self.semaphore:
                try:
                    await self.producer.send(
                        topic=self.topic,
                        value=report.model_dump(),
                    )
                    break
                except KafkaTimeoutError:
                    retries += 1
                    logger.warning(f"KafkaTimeoutError - {retries=} ")
                    await asyncio.sleep(min(2**retries, MAX_BACKOFF))
