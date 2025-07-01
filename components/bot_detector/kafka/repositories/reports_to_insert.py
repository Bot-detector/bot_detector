import logging

import orjson
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, TopicPartition
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

    async def consume_many(
        self,
        max_messages: int = 10_000,
        timeout_ms: int = 1_000,
    ) -> tuple[list[ReportsToInsertStruct], list[str]]:
        messages = await self.consumer.getmany(
            timeout_ms=timeout_ms,
            max_records=max_messages,
        )

        msg_values = [msg.value for tp, msgs in messages.items() for msg in msgs]

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
        await self.consumer.commit()
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


class RepoReportsToInsertProducer(ProducerInterface):
    def __init__(self, bootstrap_servers: str):
        self.producer = AIOKafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: orjson.dumps(v),
            acks="all",
        )
        self.topic = "reports.to_insert"

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

        await self.producer.send(
            topic=self.topic,
            value=report.model_dump(),
        )
