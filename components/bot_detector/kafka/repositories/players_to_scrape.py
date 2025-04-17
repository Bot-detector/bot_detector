import logging

import orjson
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, TopicPartition
from bot_detector.kafka.interface import (
    ConsumerInterface,
    ProducerInterface,
)
from bot_detector.structs import ToScrapeStruct

logger = logging.getLogger(__name__)


class RepoPlayersToScrapeConsumer(ConsumerInterface):
    def __init__(self, group_id: str, bootstrap_servers: list[str]):
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

    async def consume_one(self) -> ToScrapeStruct:
        msg = await self.consumer.getone()
        player = ToScrapeStruct(**msg.value)
        return player

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
            committed = await self.consumer.committed(tp)

            # Get the latest offset in the topic
            end_offset = await self.consumer.end_offsets([tp])

            # Calculate the lag for this partition
            lag = end_offset[tp] - committed

            # Add the lag for this partition to the total lag
            total_lag += lag

        return total_lag


class RepoPlayersToScrapeProducer(ProducerInterface):
    def __init__(self, bootstrap_servers: list[str]):
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
