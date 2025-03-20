import json
from dataclasses import asdict

import orjson
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from bot_detector.database.structs import PlayerStruct
from bot_detector.kafka.interface import (
    PlayersToScrapeConsumerInterface,
    PlayersToScrapeProducerInterface,
)


class RepoPlayersToScrapeConsumer(PlayersToScrapeConsumerInterface):
    def __init__(self, group_id: str):
        self.consumer = AIOKafkaConsumer(
            "players.to_scrape",
            group_id=group_id,
            value_deserializer=lambda x: orjson.loads(x),
            auto_offset_reset="earliest",
        )

    async def start(self):
        await self.consumer.start()

    async def stop(self):
        await self.consumer.stop()

    async def get_consumer(self):
        return self.consumer

    async def consume_one(self) -> PlayerStruct:
        msg = await self.consumer.getone()
        player = PlayerStruct(**msg.value)
        return player


class RepoPlayersToScrapeProducer(PlayersToScrapeProducerInterface):
    def __init__(self, bootstrap_servers: list[str]):
        self.producer = AIOKafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: orjson.dumps(v),
            acks="all",
        )

    async def start(self):
        await self.producer.start()

    async def stop(self):
        await self.producer.stop()

    async def get_producer(self):
        return self.producer

    async def produce_one(self, player: PlayerStruct):
        if not isinstance(player, PlayerStruct):
            raise Exception()

        await self.producer.send(
            topic="players.to_scrape",
            value=asdict(player),
        )
