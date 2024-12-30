import asyncio
import json

from aiokafka import AIOKafkaConsumer
from AioKafkaEngine import ConsumerEngine


class KafkaConsumer:
    def __init__(self, bootstrap_servers: str, group_id: str):
        self.bootstrap_servers = bootstrap_servers
        self.group_id = group_id

    async def consume(
        self, topic: str, queue: asyncio.Queue, batch_size: int = 1, timeout: int = 1
    ):
        """
        Consume messages from a Kafka topic and place them into a queue.

        Args:
            topic (str): Kafka topic to consume from.
            queue (asyncio.Queue): Queue to push consumed messages into.
            batch_size (int): Number of messages to consume in one batch.
            timeout (int): Timeout for consuming messages.
        """
        consumer = AIOKafkaConsumer(
            topic,
            bootstrap_servers=self.bootstrap_servers,
            group_id=self.group_id,
            value_deserializer=lambda x: json.loads(x.decode("utf-8")),
            auto_offset_reset="earliest",
        )
        engine = ConsumerEngine(
            consumer=consumer, queue=queue, batch_size=batch_size, timeout=timeout
        )
        await engine.start()
        return asyncio.create_task(engine.consume())
