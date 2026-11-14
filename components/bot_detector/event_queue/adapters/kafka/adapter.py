import asyncio
import logging
from typing import Any, Generic, Optional, TypeVar

import orjson
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, ConsumerRecord
from aiokafka.errors import KafkaError
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
from bot_detector.event_queue.core.metrics import (
    MESSAGES_SKIPPED,
)
from pydantic import BaseModel, ValidationError

from .config import KafkaConfig

T = TypeVar("T", bound=BaseModel)

POISON_KEY = "_poison"


def _deserialize_value(raw: bytes | None) -> Any:
    """Never raises: poison bytes become a dict that fails model validation.

    A raising deserializer would kill aiokafka's internal fetcher task and
    silently stall the consumer.
    """
    if raw is None:
        return None
    try:
        return orjson.loads(raw)
    except orjson.JSONDecodeError:
        return {POISON_KEY: True, "raw": raw[:200].decode("utf-8", errors="replace")}


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
        # build + assign only after a successful start: a failed start()
        # must leave producer None so the next start() actually retries
        if self.producer is None:
            producer = AIOKafkaProducer(
                bootstrap_servers=self.config.bootstrap_servers,
                value_serializer=lambda v: orjson.dumps(v),
            )
            await producer.start()
            self.producer = producer

    async def stop(self) -> None:
        if self.producer:
            await self.producer.stop()

    async def put(self, messages: list[T]) -> Optional[Exception]:
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
            while True:
                try:
                    # send_and_wait: send() alone resolves on buffering, not
                    # broker ack; awaiting only send() silently drops the
                    # delivery future and its errors
                    await self.producer.send_and_wait(
                        topic=self.config.topic,
                        value=message.model_dump(exclude_none=_config.exclude_none),
                        key=key,
                    )
                    break
                except KafkaError as e:
                    retries += 1
                    if retries >= _config.MAX_PRODUCE_RETRIES:
                        return e
                    await asyncio.sleep(
                        min(retries * 10, _config.MAX_PRODUCE_RETRY_BACKOFF)
                    )


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
        # build + assign only after a successful start: a failed start()
        # must leave consumer None so the next start() actually retries
        if self.consumer is None:
            _config = self.config.consumer_config
            consumer = AIOKafkaConsumer(
                self.config.topic,
                bootstrap_servers=self.config.bootstrap_servers,
                group_id=_config.group_id,
                auto_offset_reset=_config.auto_offset_reset,
                enable_auto_commit=_config.enable_auto_commit,
                value_deserializer=_deserialize_value,
            )
            await consumer.start()
            self.consumer = consumer

    async def stop(self) -> None:
        if self.consumer:
            await self.consumer.stop()

    async def get_one(self) -> Optional[T] | Exception:
        if self.consumer is None:
            return ConsumerNotStartedError(
                "Consumer is None, did you start the consumer?"
            )
        try:
            record = await self.consumer.getone()
        except KafkaError as e:
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
            except KafkaError as e:
                return ConsumerFetchError("Failed to fetch messages", cause=e)

            if not records:
                await asyncio.sleep(1)  # prevent busy-loop
                continue

            for consumer_records in records.values():
                for record in consumer_records:
                    _record = self._validate(record=record)
                    if isinstance(_record, Exception):
                        # skip, never return: returning would discard the
                        # whole batch and stall the partition forever,
                        # because the offset only advances on commit after
                        # a successful get_many (commit-after-dequeue)
                        MESSAGES_SKIPPED.inc()
                        self.logger.warning(f"skipping invalid record: {_record}")
                        continue
                    batcher.append(_record, auto=False)
        return batcher.flush()

    async def commit(self) -> Optional[Exception]:
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

    async def put(self, messages: list[T]) -> Optional[Exception]:
        return await self.producer.put(messages)

    async def get_one(self) -> Optional[T] | Exception:
        return await self.consumer.get_one()

    async def get_many(self, count: int) -> list[T] | Exception:
        return await self.consumer.get_many(count)

    async def commit(self) -> Optional[Exception]:
        return await self.consumer.commit()
