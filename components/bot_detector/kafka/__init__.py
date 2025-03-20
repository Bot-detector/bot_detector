from pydantic_settings import BaseSettings

from .consumer import KafkaConsumer
from .producer import KafkaProducer


class Settings(BaseSettings):
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9094"


__all__ = ["KafkaConsumer", "KafkaProducer", "Settings"]
