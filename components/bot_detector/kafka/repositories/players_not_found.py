import orjson
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from bot_detector.kafka.interface import (
    ConsumerInterface,
    ProducerInterface,
)
from bot_detector.structs import NotFoundStruct


class RepoPlayersNotFoundConsumer(ConsumerInterface):
    def __init__(self, group_id: str, bootstrap_servers: list[str]):
        self.consumer = AIOKafkaConsumer(
            "players.not_found",
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

    async def consume_one(self) -> NotFoundStruct:
        msg = await self.consumer.getone()
        player = NotFoundStruct(**msg.value)
        return player


class RepoPlayersNotFoundProducer(ProducerInterface):
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

    async def produce_one(self, player: NotFoundStruct):
        if not isinstance(player, NotFoundStruct):
            raise Exception()

        await self.producer.send(
            topic="players.not_found",
            value=player.model_dump(),
        )
