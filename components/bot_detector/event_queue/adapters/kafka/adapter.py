import asyncio
import logging
from typing import Generic, TypeVar

import orjson
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, ConsumerRecord
from aiokafka.errors import KafkaTimeoutError
from bot_detector.event_queue.core.batcher import Batcher
from bot_detector.event_queue.core.errors import (
    ConsumerConfigError,
    ConsumerFetchError,
    ConsumerNotStartedError,
    MessageTypeError,
    ProducerConfigError,
    ProducerNotStartedError,
)
from bot_detector.event_queue.core.interface import (
    QueueBackendConsumerProtocol,
    QueueBackendProducerProtocol,
    QueueBackendProtocol,
)
from pydantic import BaseModel, ValidationError

from .config import KafkaConfig

T = TypeVar("T", bound=BaseModel)


class _AIOKafkaProducerBase(Generic[T]):
    """
    Adapts the aiokafka library to the QueueBackendProtocol.
    Manages both a Producer and a Consumer internally.
    """

    def __init__(self, cls: type[T], config: KafkaConfig):
        self.config = config
        self.cls = cls
        self.logger = logging.getLogger(cls.__name__)

    def _validate(self, record: ConsumerRecord) -> T | Exception:
        if not isinstance(record.value, dict):
            return MessageTypeError("Message must be of type dict")
        try:
            return self.cls.model_validate(record.value)
        except ValidationError as ve:
            return ve


class AIOKafkaProducerAdapter(
    _AIOKafkaProducerBase[T],
    QueueBackendProducerProtocol[T],
):
    """
    Adapts the aiokafka library to the QueueBackendProtocol.
    Manages both a Producer and a Consumer internally.
    """

    producer = None

    async def start(self) -> None:
        if self.producer is None:
            self.producer = AIOKafkaProducer(
                bootstrap_servers=self.config.bootstrap_servers,
                value_serializer=lambda v: orjson.dumps(v),
            )
            await self.producer.start()

    async def stop(self) -> None:
        if self.producer:
            await self.producer.stop()

    async def put(self, messages: list[T]) -> Exception | None:
        if self.producer is None:
            return ProducerNotStartedError(
                "Producer is None, did you start the producer?"
            )
        if self.config.producer_config is None:
            return ProducerConfigError("Producer Configuration is None")
        _config = self.config.producer_config

        for message in messages:
            key = None
            if _config.partition_key_fn is not None:
                raw_key = _config.partition_key_fn(message)
                if isinstance(raw_key, bytes):
                    key = raw_key
                elif isinstance(raw_key, str):
                    key = raw_key.encode("utf-8")
                else:
                    raise ValueError("partition_key_fn must return bytes or str")
            retries = 0
            retry_backoff = 0
            while True:
                try:
                    await self.producer.send(
                        topic=self.config.topic,
                        value=message.model_dump(),
                        key=key,
                    )
                    break
                except KafkaTimeoutError as e:
                    retries += 1
                    retry_backoff = min(
                        retries * 10,
                        _config.MAX_PRODUCE_RETRY_BACKOFF,
                    )
                    await asyncio.sleep(retry_backoff)
                    if _config.MAX_PRODUCE_RETRIES == retries:
                        return e


class AIOKafkaConsumerAdapter(
    _AIOKafkaProducerBase[T],
    QueueBackendConsumerProtocol[T],
):
    """
    Adapts the aiokafka library to the QueueBackendProtocol.
    Manages both a Producer and a Consumer internally.
    """

    consumer = None

    async def start(self) -> None:
        if self.config.consumer_config is None:
            raise ConsumerConfigError("Consumer Configuration is None")
        if self.consumer is None:
            _config = self.config.consumer_config
            self.consumer = AIOKafkaConsumer(
                self.config.topic,
                bootstrap_servers=self.config.bootstrap_servers,
                group_id=_config.group_id,
                auto_offset_reset=_config.auto_offset_reset,
                enable_auto_commit=_config.enable_auto_commit,
                value_deserializer=lambda x: orjson.loads(x),
            )
            await self.consumer.start()

    async def stop(self) -> None:
        if self.consumer:
            await self.consumer.stop()

    async def get_one(self) -> T | None | Exception:
        if self.consumer is None:
            return ConsumerNotStartedError(
                "Consumer is None, did you start the consumer?"
            )
        try:
            record = await self.consumer.getone()
        except Exception as e:
            return ConsumerFetchError("Failed to fetch message", cause=e)
        if record is None:
            return None

        message = self._validate(record=record)
        return message

    async def get_many(self, count: int) -> list[T] | Exception:
        if self.consumer is None:
            return ConsumerNotStartedError(
                "Consumer is None, did you start the consumer?"
            )
        if self.config.consumer_config is None:
            return ConsumerConfigError("Consumer Configuration is None")
        _config = self.config.consumer_config

        batcher = Batcher[T](
            batch_size=count,
            timeout_ms=_config.consume_timeout_ms,
        )
        while not batcher.check_flush():
            remaining_ms = int(batcher.time_left * 1000)
            if remaining_ms <= 0:
                break

            try:
                records = await self.consumer.getmany(
                    timeout_ms=remaining_ms,
                    max_records=count - batcher.size,
                )
            except Exception as e:
                return ConsumerFetchError("Failed to fetch messages", cause=e)

            if not records:
                await asyncio.sleep(1)  # prevent busy-loop
                continue

            for consumer_records in records.values():
                for record in consumer_records:
                    _record = self._validate(record=record)
                    if isinstance(_record, Exception):
                        return _record
                    batcher.append(_record, auto=False)
        return batcher.flush()

    async def commit(self) -> Exception | None:
        if self.consumer is None:
            return ConsumerNotStartedError(
                "Consumer is None, did you start the consumer?"
            )
        return await self.consumer.commit()


class AIOKafkaAdapter(QueueBackendProtocol[T]):
    """
    Adapts the aiokafka library to the QueueBackendProtocol.
    Manages both a Producer and a Consumer internally.
    """

    def __init__(self, cls: type[T], config: KafkaConfig):
        self.config = config
        self.producer = AIOKafkaProducerAdapter(cls, config)
        self.consumer = AIOKafkaConsumerAdapter(cls, config)

    async def start(self) -> None:
        if self.config.producer:
            await self.producer.start()
        if self.config.consumer:
            await self.consumer.start()

    async def stop(self) -> None:
        if self.consumer:
            await self.consumer.stop()
        if self.producer:
            await self.producer.stop()

    async def put(self, messages: list[T]) -> Exception | None:
        return await self.producer.put(messages)

    async def get_one(self) -> T | None | Exception:
        return await self.consumer.get_one()

    async def get_many(self, count: int) -> list[T] | Exception:
        return await self.consumer.get_many(count)

    async def commit(self) -> Exception | None:
        return await self.consumer.commit()
