from typing import Any, Callable, Optional, TypeVar

from pydantic import BaseModel, Field, model_validator

T = TypeVar("T", bound=BaseModel)


class KafkaConsumerConfig(BaseModel):
    group_id: str
    auto_offset_reset: str = "earliest"
    enable_auto_commit: bool = False
    consume_timeout_ms: int = Field(default=5_000, ge=1)


class KafkaProducerConfig(BaseModel):
    partition_key_fn: Optional[Callable[[Any], bytes | str]] = None
    # ge=1: retries=0 would make the retry loop's cap unreachable (infinite)
    MAX_PRODUCE_RETRIES: int = Field(default=3, ge=1)
    MAX_PRODUCE_RETRY_BACKOFF: int = Field(default=60, ge=0)
    # drop null-valued fields from model_dump() payloads; consumers
    # rehydrate Optionals as None, so slim payloads validate identically
    exclude_none: bool = False


class KafkaConfig(BaseModel):
    topic: str
    bootstrap_servers: str
    consumer: bool = False
    producer: bool = False
    producer_config: Optional[KafkaProducerConfig] = None
    consumer_config: Optional[KafkaConsumerConfig] = None

    @model_validator(mode="after")
    def check_config(self):
        if self.consumer and self.consumer_config is None:
            raise ValueError("consumer cannot be True when consumer_config is None")
        if self.producer and self.producer_config is None:
            raise ValueError("producer cannot be True when producer_config is None")
        return self
