import logging

import orjson
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, TopicPartition
from bot_detector.kafka.interface import (
    ConsumerInterface,
    ProducerInterface,
)
from bot_detector.core.structs import NotFoundStruct

logger = logging.getLogger(__name__)


class RepoPlayersNotFoundConsumer(ConsumerInterface):
    def __init__(
        self,
        group_id: str,
        bootstrap_servers: str,
        enable_auto_commit: bool = True,
    ):
        self.consumer = AIOKafkaConsumer(
            "players.not_found",
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
        if "player_data" not in value:
            return None, "Missing required field 'player_data' in message value"
        return value, None

    async def consume_one(self) -> NotFoundStruct:
        msg = await self.consumer.getone()
        value, error = self._validate_value(value=msg.value)

        if error:
            raise ValueError(f"Invalid message value: {error}")

        if not value:
            raise ValueError("Message value is None")

        player = NotFoundStruct(
            metadata=value["metadata"],
            player_data=value["player_data"],
        )
        return player

    async def consume_many(
        self,
        max_messages: int = 10_000,
        timeout_ms: int = 1_000,
    ):
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

            report = NotFoundStruct(
                metadata=value["metadata"],
                player_data=value["player_data"],
            )
            players.append(report)
        return players, errors

    async def get_lag(self) -> int:
        total_lag = 0
        topic = "players.not_found"

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


class RepoPlayersNotFoundProducer(ProducerInterface):
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

    async def produce_one(self, player: NotFoundStruct):
        if not isinstance(player, NotFoundStruct):
            raise Exception()

        await self.producer.send(
            topic="players.not_found",
            value=player.model_dump(),
        )
