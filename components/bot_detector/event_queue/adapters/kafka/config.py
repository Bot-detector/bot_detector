from typing import Callable, Optional, TypeVar

from pydantic import BaseModel, model_validator

T = TypeVar("T", bound=BaseModel)


class KafkaConsumerConfig(BaseModel):
    group_id: str
    auto_offset_reset: str = "earliest"
    enable_auto_commit: bool = False
    consume_timeout_ms: int = 5_000


class KafkaProducerConfig(BaseModel):
    partition_key_fn: Callable
    MAX_PRODUCE_RETRIES: int = 3
    MAX_PRODUCE_RETRY_BACKOFF: int = 60


class KafkaConfig(BaseModel):
    topic: str
    bootstrap_servers: str
    consumer: bool = True
    producer: bool = True
    producer_config: Optional[KafkaProducerConfig]
    consumer_config: Optional[KafkaConsumerConfig]

    @model_validator(mode="after")
    def check_config(self):
        if self.consumer and self.consumer_config is None:
            raise ValueError("consumer cannot be True when consumer_config is None")
        if self.producer and self.producer_config is None:
            raise ValueError("producer cannot be True when producer_config is None")
        return self
