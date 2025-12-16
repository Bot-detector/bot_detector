import asyncio
import logging

import orjson
from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaTimeoutError
from bot_detector.kafka.core.producer_interface import ProducerInterface

logger = logging.getLogger(__name__)


class BaseProducer(ProducerInterface):
    def __init__(self, bootstrap_servers: str, topic: str | None = None):
        self.topic = topic
        self._producer = AIOKafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: orjson.dumps(v),
            acks="all",
        )

    async def start(self):
        await self._producer.start()
        return self._producer

    async def stop(self):
        await self._producer.stop()

    async def get_producer(self):
        return self._producer

    async def produce_one(
        self,
        data: dict,
        topic: str | None = None,
        partition_key: bytes | None = None,
    ):
        # Use the provided topic or fall back to the default topic
        _topic = topic or self.topic
        assert _topic is not None, "Topic must be specified"

        retries = 0
        MAX_BACKOFF = 60
        while True:
            try:
                await self._producer.send(
                    topic=_topic,
                    value=data,
                    key=partition_key,
                )
                break
            except KafkaTimeoutError:
                retries += 1
                logger.warning(f"KafkaTimeoutError - {topic=} {retries=} ")
                await asyncio.sleep(min(2**retries, MAX_BACKOFF))
