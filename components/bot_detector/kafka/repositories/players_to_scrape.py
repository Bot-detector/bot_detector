import logging

import orjson
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, TopicPartition
from bot_detector.kafka.interface import (
    ConsumerInterface,
    ProducerInterface,
)
from bot_detector.core.structs import ToScrapeStruct

logger = logging.getLogger(__name__)


class RepoPlayersToScrapeConsumer(ConsumerInterface):
    def __init__(self, group_id: str, bootstrap_servers: str):
        self.consumer = AIOKafkaConsumer(
            "players.to_scrape",
            group_id=group_id,
            value_deserializer=lambda x: orjson.loads(x),
            auto_offset_reset="earliest",
            bootstrap_servers=bootstrap_servers,
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
        if "player_data" not in value:
            return None, "Missing required field 'player_data' in message value"
        return value, None

    async def consume_one(self) -> ToScrapeStruct:
        msg = await self.consumer.getone()
        value, error = self._validate_value(value=msg.value)

        if error:
            raise ValueError(f"Invalid message value: {error}")

        if not value:
            raise ValueError("Message value is None")

        player = ToScrapeStruct(
            metadata=value["metadata"],
            player_data=value["player_data"],
        )
        return player

    async def consume_many(
        self, max_messages: int = 1_000, timeout_ms: int = 1000
    ) -> tuple[list[ToScrapeStruct], list[str]]:
        messages = await self.consumer.getmany(
            timeout_ms=timeout_ms,
            max_records=max_messages,
        )

        msg_values = [msg.value for tp, msgs in messages.items() for msg in msgs]

        players, errors = [], []

        for value in msg_values:
            value, error = self._validate_value(value)

            if error:
                errors.append(error)
                continue

            if not value:
                errors.append("Message value is None")
                continue

            player = ToScrapeStruct(
                metadata=value["metadata"],
                player_data=value["player_data"],
            )
            players.append(player)

        return players, errors

    async def get_lag(self) -> int:
        total_lag = 0
        topic = "players.to_scrape"

        # Get the list of partitions for the topic
        partitions = self.consumer.partitions_for_topic(topic)

        if partitions is None:
            logger.warning("partitions is none")
            return 0

        for partition in partitions:
            tp = TopicPartition(topic, partition)

            # Get the last offset committed by the consumer
            committed = await self.consumer.committed(tp) or 0

            # Get the latest offset in the topic
            end_offset = await self.consumer.end_offsets([tp])

            # Calculate the lag for this partition
            lag = end_offset[tp] - committed

            # Add the lag for this partition to the total lag
            total_lag += lag

        return total_lag


class RepoPlayersToScrapeProducer(ProducerInterface):
    def __init__(self, bootstrap_servers: str):
        self.producer = AIOKafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: orjson.dumps(v),
            acks="all",
        )

    async def start(self):
        await self.producer.start()
        return self

    async def stop(self):
        await self.producer.stop()

    async def get_producer(self):
        return self.producer

    async def produce_one(self, player: ToScrapeStruct):
        if not isinstance(player, ToScrapeStruct):
            raise Exception()

        await self.producer.send(
            topic="players.to_scrape",
            value=player.model_dump(),
        )
