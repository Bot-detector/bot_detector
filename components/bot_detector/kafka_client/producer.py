import asyncio
import json

from aiokafka import AIOKafkaProducer
from AioKafkaEngine import ProducerEngine


class KafkaProducer:
    def __init__(self, bootstrap_servers: str):
        self.bootstrap_servers = bootstrap_servers

    async def produce(self, topic: str, queue: asyncio.Queue):
        """
        Produce messages to a Kafka topic from a queue.

        Args:
            topic (str): Kafka topic to produce to.
            queue (asyncio.Queue): Queue to pull messages from and produce.
        """
        producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode(),
            acks="all",
        )
        engine = ProducerEngine(producer=producer, queue=queue, topic=topic)
        await engine.start()
        return asyncio.create_task(engine.produce())
