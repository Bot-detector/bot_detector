import logging

from bot_detector.kafka.core.base_consumer import BaseConsumer
from bot_detector.kafka.core.base_producer import BaseProducer

logger = logging.getLogger(__name__)


class KafkaManager:
    def __init__(self):
        self.producers = {}
        self.consumers = {}
        logger.debug("KafkaManager initialized.")

    def set_producer(self, key: str, producer: BaseProducer) -> None:
        self.producers[key] = producer
        logger.debug(f"Producer set for key: {key}")

    def get_producer(self, key: str | None) -> BaseProducer | None:
        logger.debug(f"Retrieving producer for key: {key}")

        if key is None:
            return self.producers

        producer = self.producers.get(key)

        if not producer:
            logger.debug(self.producers)
            logger.warning(f"Producer not found for key: {key}")
            return None

        logger.debug(f"Producer retrieved for key: {key}")
        return producer

    def set_consumer(self, key: str, consumer: BaseConsumer) -> None:
        self.consumers[key] = consumer
        logger.debug(f"Consumer set for key: {key}")

    def get_consumer(self, key: str | None) -> BaseConsumer | None:
        if key is None:
            return self.consumers

        consumer = self.consumers.get(key)

        if not consumer:
            logger.debug(self.consumers)
            logger.warning(f"Consumer not found for key: {key}")
            return None

        logger.debug(f"Consumer retrieved for key: {key}")
        return consumer


# Create a global KafkaManager instance
kafka_manager = KafkaManager()

# memory location
# print(id(kafka_manager))
