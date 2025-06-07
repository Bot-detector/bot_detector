import asyncio
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from asyncio import Queue
import json

def retry_on_exception(max_retries=3, retry_interval=5):
    def decorator(func):
        async def wrapper(*args, **kwargs):
            retries = 0
            while retries < max_retries:
                try:
                    await func(*args, **kwargs)
                except Exception as e:
                    print(f"Error: {e}")
                    retries += 1
                    await asyncio.sleep(retry_interval)
                else:
                    break
        return wrapper
    return decorator

class AioKafkaEngine:
    def __init__(self, bootstrap_servers: list[str], topic: str, message_queue: Queue):
        self.bootstrap_servers = bootstrap_servers
        self.topic = topic
        self.consumer = None
        self.producer = None
        self.message_queue = message_queue

    async def start_consumer(self, group_id: str):
        self.consumer = AIOKafkaConsumer(
            self.topic,
            bootstrap_servers=self.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode(),
            group_id=group_id,
        )
        await self.consumer.start()

    async def start_producer(self):
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode()
        )
        await self.producer.start()

    @retry_on_exception(max_retries=3, retry_interval=5)
    async def consume_messages(self):
        if self.consumer is None:
            raise ValueError("Consumer not started. Call start_consumer() first.")

        async for message in self.consumer:
            value = message.value
            self.message_queue.put_nowait(value)
    
    @retry_on_exception(max_retries=3, retry_interval=5)
    async def produce_messages(self):
        if self.producer is None:
            raise ValueError("Producer not started. Call start_producer() first.")
        while True:
            message = await self.message_queue.get()
            await self.producer.send(self.topic, value=message)

    async def stop_consumer(self):
        if self.consumer:
            await self.consumer.stop()

    async def stop_producer(self):
        if self.producer:
            await self.producer.stop()
    
    def is_ready(self):
        return self.consumer is not None or self.producer is not None