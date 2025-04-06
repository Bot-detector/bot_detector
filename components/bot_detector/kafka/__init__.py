from pydantic_settings import BaseSettings

from .consumer import KafkaConsumer
from .producer import KafkaProducer


class Settings(BaseSettings):
    KAFKA_BOOTSTRAP_SERVERS: str


__all__ = ["KafkaConsumer", "KafkaProducer", "Settings"]
