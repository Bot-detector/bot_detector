import logging
import time

import orjson
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, TopicPartition
from bot_detector.kafka.interface import (
    ConsumerInterface,
    ProducerInterface,
)
from bot_detector.core.structs import ScrapedStruct

logger = logging.getLogger(__name__)


class RepoPlayerScrapedConsumer(ConsumerInterface):
    def __init__(self, group_id: str, bootstrap_servers: str):
        self.consumer = AIOKafkaConsumer(
            "players.scraped",
            group_id=group_id,
            value_deserializer=lambda x: orjson.loads(x),
            auto_offset_reset="earliest",
            bootstrap_servers=bootstrap_servers,
        )

    async def start(self):
        await self.consumer.start()
        return self

    async def stop(self):
        await self.consumer.stop()

    async def get_consumer(self):
        return self.consumer

    def _validate_value(self, value) -> tuple[dict | None, str | None]:
        if not isinstance(value, dict):
            return None, "Message value is not a dict"
        if "metadata" not in value:
            return None, "Missing required field 'metadata' in message value"
        if "player_data" not in value:
            return None, "Missing required field 'player_data' in message value"
        if "highscore_data" not in value:
            return None, "Missing required field 'highscore_data' in message value"
        return value, None

    async def consume_one(self) -> ScrapedStruct:
        msg = await self.consumer.getone()
        value, error = self._validate_value(value=msg.value)

        if error:
            raise ValueError(f"Invalid message value: {error}")

        if not value:
            raise ValueError("Message value is None")
        scraped = ScrapedStruct(
            metadata=value["metadata"],
            player_data=value["player_data"],
            highscore_data=value["highscore_data"],
        )
        return scraped

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
        self, max_messages: int, timeout_ms: int
    ) -> tuple[list[ScrapedStruct], list[str]]:
        msg_values = await self.buffer_records(
            max_records=max_messages,
            timeout_ms=timeout_ms,
        )

        scraped_records, errors = [], []

        for value in msg_values:
            value, error = self._validate_value(value)

            if error:
                errors.append(error)
                continue

            if not value:
                errors.append("Message value is None")
                continue

            scraped = ScrapedStruct(
                metadata=value["metadata"],
                player_data=value["player_data"],
                highscore_data=value["highscore_data"],
            )

            scraped_records.append(scraped)
        return scraped_records, errors

    async def get_lag(self) -> int:
        total_lag = 0
        topic = "players.scraped"

        # Get the list of partitions for the topic
        partitions = self.consumer.partitions_for_topic(topic)

        if partitions is None:
            logger.warning("partitions is none")
            return 0

        for partition in partitions:
            tp = TopicPartition(topic, partition)

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


class RepoPlayerScrapedProducer(ProducerInterface):
    def __init__(self, bootstrap_servers: str):
        self.producer = AIOKafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: orjson.dumps(v),
            acks="all",
        )

    async def start(self):
        await self.producer.start()
        return self.producer

    async def stop(self):
        await self.producer.stop()

    async def get_producer(self):
        return self.producer

    async def produce_one(self, scraped_data: ScrapedStruct):
        if not isinstance(scraped_data, ScrapedStruct):
            raise Exception()

        player_id = scraped_data.player_data.id
        partition_key = str(player_id % 10).encode("utf-8")

        await self.producer.send(
            topic="players.scraped",
            value=scraped_data.model_dump(),
            key=partition_key,  # db table is partitioned on player_id % 10
        )
