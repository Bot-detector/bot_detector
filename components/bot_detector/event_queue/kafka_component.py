from typing import Generic, Literal, TypeVar, cast

from bot_detector.event_queue.adapters.kafka import (
    KafkaConfig,
    KafkaConsumerConfig,
    KafkaProducerConfig,
)
from bot_detector.event_queue.adapters.memory import InMemoryConfig
from bot_detector.event_queue.core import Queue, QueueConsumer, QueueProducer
from bot_detector.event_queue.factory import QueueFactory
from bot_detector.event_queue.structs import (
    DataToPredictStruct,
    HighScoreStruct,
    NotFoundStruct,
    ReportsToInsertStruct,
    ScrapedStruct,
    ToScrapeStruct,
)
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

T = TypeVar("T", bound=BaseModel)
BackendType = Literal["kafka", "memory"]


class Settings(BaseSettings):
    KAFKA_BOOTSTRAP_SERVERS: str = Field(default=...)


def _default_backend_config(
    backend_type: BackendType,
    queue_type: Literal["queue", "producer", "consumer"],
    topic: str,
    bootstrap_servers: str | None,
    partition_key_fn,
    group_id: str | None,
    enable_auto_commit: bool,
    timeout_ms: int,
) -> KafkaConfig | InMemoryConfig:
    if backend_type == "memory":
        return InMemoryConfig()

    if bootstrap_servers is None:
        raise ValueError("bootstrap_servers is required when backend_type='kafka'")

    return KafkaConfig(
        topic=topic,
        bootstrap_servers=bootstrap_servers,
        producer=queue_type in {"queue", "producer"},
        consumer=queue_type in {"queue", "consumer"},
        producer_config=(
            KafkaProducerConfig(partition_key_fn=partition_key_fn)
            if queue_type in {"queue", "producer"}
            else None
        ),
        consumer_config=(
            KafkaConsumerConfig(
                group_id=group_id or "default",
                enable_auto_commit=enable_auto_commit,
                consume_timeout_ms=timeout_ms,
            )
            if queue_type in {"queue", "consumer"}
            else None
        ),
    )


def _build_queue(
    model: type[T],
    queue_type: Literal["queue", "producer", "consumer"],
    backend_type: BackendType,
    backend_config: KafkaConfig | InMemoryConfig,
) -> Queue[T] | QueueProducer[T] | QueueConsumer[T]:
    queue = QueueFactory.create_queue(
        model=model,
        queue_type=queue_type,
        backend_type=backend_type,
        config=backend_config,
    )
    if isinstance(queue, Exception):
        raise queue
    return queue


class _BaseProducerFacade(Generic[T]):
    def __init__(
        self,
        model: type[T],
        topic: str,
        partition_key_fn,
        bootstrap_servers: str | None,
        backend_type: BackendType,
        backend_config: KafkaConfig | InMemoryConfig | None,
    ):
        config = backend_config or _default_backend_config(
            backend_type=backend_type,
            queue_type="producer",
            topic=topic,
            bootstrap_servers=bootstrap_servers,
            partition_key_fn=partition_key_fn,
            group_id=None,
            enable_auto_commit=True,
            timeout_ms=5_000,
        )
        self._producer = cast(
            QueueProducer[T],
            _build_queue(
                model=model,
                queue_type="producer",
                backend_type=backend_type,
                backend_config=config,
            ),
        )

    async def start(self):
        await self._producer.start()

    async def stop(self):
        await self._producer.stop()

    async def produce_one(self, message: T, topic: str | None = None, **_kwargs):
        _ = topic
        await self._producer.put([message])


class _BaseConsumerFacade(Generic[T]):
    def __init__(
        self,
        model: type[T],
        topic: str,
        group_id: str,
        bootstrap_servers: str | None,
        enable_auto_commit: bool,
        backend_type: BackendType,
        backend_config: KafkaConfig | InMemoryConfig | None,
    ):
        self._consumer_config = backend_config or _default_backend_config(
            backend_type=backend_type,
            queue_type="consumer",
            topic=topic,
            bootstrap_servers=bootstrap_servers,
            partition_key_fn=lambda _: "0",
            group_id=group_id,
            enable_auto_commit=enable_auto_commit,
            timeout_ms=5_000,
        )
        self._consumer = cast(
            QueueConsumer[T],
            _build_queue(
                model=model,
                queue_type="consumer",
                backend_type=backend_type,
                backend_config=self._consumer_config,
            ),
        )

    async def start(self):
        await self._consumer.start()

    async def stop(self):
        await self._consumer.stop()

    async def consume_many(self, max_records: int, timeout_ms: int):
        if isinstance(self._consumer_config, KafkaConfig):
            self._consumer_config.consumer_config.consume_timeout_ms = timeout_ms

        result = await self._consumer.get_many(count=max_records)
        if isinstance(result, Exception):
            return [], [str(result)]
        return result, []

    async def commit(self):
        error = await self._consumer.commit()
        if isinstance(error, Exception):
            raise error


class _BaseQueueFacade(Generic[T]):
    def __init__(
        self,
        model: type[T],
        topic: str,
        partition_key_fn,
        group_id: str,
        bootstrap_servers: str | None,
        enable_auto_commit: bool,
        backend_type: BackendType,
        backend_config: KafkaConfig | InMemoryConfig | None,
    ):
        self._queue_config = backend_config or _default_backend_config(
            backend_type=backend_type,
            queue_type="queue",
            topic=topic,
            bootstrap_servers=bootstrap_servers,
            partition_key_fn=partition_key_fn,
            group_id=group_id,
            enable_auto_commit=enable_auto_commit,
            timeout_ms=5_000,
        )
        self._queue = cast(
            Queue[T],
            _build_queue(
                model=model,
                queue_type="queue",
                backend_type=backend_type,
                backend_config=self._queue_config,
            ),
        )

    async def start(self):
        await self._queue.start()

    async def stop(self):
        await self._queue.stop()

    async def produce_one(self, message: T, topic: str | None = None, **_kwargs):
        _ = topic
        await self._queue.put([message])

    async def consume_many(self, max_records: int, timeout_ms: int):
        if isinstance(self._queue_config, KafkaConfig):
            self._queue_config.consumer_config.consume_timeout_ms = timeout_ms

        result = await self._queue.get_many(count=max_records)
        if isinstance(result, Exception):
            return [], [str(result)]
        return result, []

    async def commit(self):
        error = await self._queue.commit()
        if isinstance(error, Exception):
            raise error


class PlayersToScrapeProducer(_BaseProducerFacade[ToScrapeStruct]):
    def __init__(
        self,
        bootstrap_servers: str | None,
        max_async_actions: int = 10,
        backend_type: BackendType = "kafka",
        backend_config: KafkaConfig | InMemoryConfig | None = None,
    ):
        _ = max_async_actions
        super().__init__(
            model=ToScrapeStruct,
            topic="players.to_scrape",
            partition_key_fn=lambda message: str(message.player_data.id % 10),
            bootstrap_servers=bootstrap_servers,
            backend_type=backend_type,
            backend_config=backend_config,
        )


class PlayersToScrapeConsumer(_BaseConsumerFacade[ToScrapeStruct]):
    def __init__(
        self,
        group_id: str,
        bootstrap_servers: str | None,
        enable_auto_commit: bool = True,
        backend_type: BackendType = "kafka",
        backend_config: KafkaConfig | InMemoryConfig | None = None,
    ):
        super().__init__(
            model=ToScrapeStruct,
            topic="players.to_scrape",
            group_id=group_id,
            bootstrap_servers=bootstrap_servers,
            enable_auto_commit=enable_auto_commit,
            backend_type=backend_type,
            backend_config=backend_config,
        )


class PlayersToScrapeQueue(_BaseQueueFacade[ToScrapeStruct]):
    def __init__(
        self,
        group_id: str,
        bootstrap_servers: str | None,
        enable_auto_commit: bool = True,
        backend_type: BackendType = "kafka",
        backend_config: KafkaConfig | InMemoryConfig | None = None,
    ):
        super().__init__(
            model=ToScrapeStruct,
            topic="players.to_scrape",
            partition_key_fn=lambda message: str(message.player_data.id % 10),
            group_id=group_id,
            bootstrap_servers=bootstrap_servers,
            enable_auto_commit=enable_auto_commit,
            backend_type=backend_type,
            backend_config=backend_config,
        )


class PlayersScrapedProducer(_BaseProducerFacade[ScrapedStruct]):
    def __init__(
        self,
        bootstrap_servers: str | None,
        max_async_actions: int = 10,
        backend_type: BackendType = "kafka",
        backend_config: KafkaConfig | InMemoryConfig | None = None,
    ):
        _ = max_async_actions
        super().__init__(
            model=ScrapedStruct,
            topic="players.scraped",
            partition_key_fn=lambda message: str(message.player_data.id % 10),
            bootstrap_servers=bootstrap_servers,
            backend_type=backend_type,
            backend_config=backend_config,
        )


class PlayersScrapedConsumer(_BaseConsumerFacade[ScrapedStruct]):
    def __init__(
        self,
        group_id: str,
        bootstrap_servers: str | None,
        enable_auto_commit: bool = True,
        backend_type: BackendType = "kafka",
        backend_config: KafkaConfig | InMemoryConfig | None = None,
    ):
        super().__init__(
            model=ScrapedStruct,
            topic="players.scraped",
            group_id=group_id,
            bootstrap_servers=bootstrap_servers,
            enable_auto_commit=enable_auto_commit,
            backend_type=backend_type,
            backend_config=backend_config,
        )


class PlayersScrapedQueue(_BaseQueueFacade[ScrapedStruct]):
    def __init__(
        self,
        group_id: str,
        bootstrap_servers: str | None,
        enable_auto_commit: bool = True,
        backend_type: BackendType = "kafka",
        backend_config: KafkaConfig | InMemoryConfig | None = None,
    ):
        super().__init__(
            model=ScrapedStruct,
            topic="players.scraped",
            partition_key_fn=lambda message: str(message.player_data.id % 10),
            group_id=group_id,
            bootstrap_servers=bootstrap_servers,
            enable_auto_commit=enable_auto_commit,
            backend_type=backend_type,
            backend_config=backend_config,
        )


class PlayersNotFoundProducer(_BaseProducerFacade[NotFoundStruct]):
    def __init__(
        self,
        bootstrap_servers: str | None,
        max_async_actions: int = 10,
        backend_type: BackendType = "kafka",
        backend_config: KafkaConfig | InMemoryConfig | None = None,
    ):
        _ = max_async_actions
        super().__init__(
            model=NotFoundStruct,
            topic="players.not_found",
            partition_key_fn=lambda message: str(message.player_data.id % 10),
            bootstrap_servers=bootstrap_servers,
            backend_type=backend_type,
            backend_config=backend_config,
        )


class PlayersNotFoundConsumer(_BaseConsumerFacade[NotFoundStruct]):
    def __init__(
        self,
        group_id: str,
        bootstrap_servers: str | None,
        enable_auto_commit: bool = True,
        backend_type: BackendType = "kafka",
        backend_config: KafkaConfig | InMemoryConfig | None = None,
    ):
        super().__init__(
            model=NotFoundStruct,
            topic="players.not_found",
            group_id=group_id,
            bootstrap_servers=bootstrap_servers,
            enable_auto_commit=enable_auto_commit,
            backend_type=backend_type,
            backend_config=backend_config,
        )


class PlayersNotFoundQueue(_BaseQueueFacade[NotFoundStruct]):
    def __init__(
        self,
        group_id: str,
        bootstrap_servers: str | None,
        enable_auto_commit: bool = True,
        backend_type: BackendType = "kafka",
        backend_config: KafkaConfig | InMemoryConfig | None = None,
    ):
        super().__init__(
            model=NotFoundStruct,
            topic="players.not_found",
            partition_key_fn=lambda message: str(message.player_data.id % 10),
            group_id=group_id,
            bootstrap_servers=bootstrap_servers,
            enable_auto_commit=enable_auto_commit,
            backend_type=backend_type,
            backend_config=backend_config,
        )


class ReportsToInsertProducer(_BaseProducerFacade[ReportsToInsertStruct]):
    def __init__(
        self,
        bootstrap_servers: str | None,
        max_async_actions: int = 10,
        backend_type: BackendType = "kafka",
        backend_config: KafkaConfig | InMemoryConfig | None = None,
    ):
        _ = max_async_actions
        super().__init__(
            model=ReportsToInsertStruct,
            topic="reports.to_insert",
            partition_key_fn=lambda message: str(message.report.reported_ts),
            bootstrap_servers=bootstrap_servers,
            backend_type=backend_type,
            backend_config=backend_config,
        )


class ReportsToInsertConsumer(_BaseConsumerFacade[ReportsToInsertStruct]):
    def __init__(
        self,
        group_id: str,
        bootstrap_servers: str | None,
        enable_auto_commit: bool = True,
        backend_type: BackendType = "kafka",
        backend_config: KafkaConfig | InMemoryConfig | None = None,
    ):
        super().__init__(
            model=ReportsToInsertStruct,
            topic="reports.to_insert",
            group_id=group_id,
            bootstrap_servers=bootstrap_servers,
            enable_auto_commit=enable_auto_commit,
            backend_type=backend_type,
            backend_config=backend_config,
        )


class ReportsToInsertQueue(_BaseQueueFacade[ReportsToInsertStruct]):
    def __init__(
        self,
        group_id: str,
        bootstrap_servers: str | None,
        enable_auto_commit: bool = True,
        backend_type: BackendType = "kafka",
        backend_config: KafkaConfig | InMemoryConfig | None = None,
    ):
        super().__init__(
            model=ReportsToInsertStruct,
            topic="reports.to_insert",
            partition_key_fn=lambda message: str(message.report.reported_ts),
            group_id=group_id,
            bootstrap_servers=bootstrap_servers,
            enable_auto_commit=enable_auto_commit,
            backend_type=backend_type,
            backend_config=backend_config,
        )


class DataToPredictProducer(_BaseProducerFacade[DataToPredictStruct]):
    def __init__(
        self,
        bootstrap_servers: str | None,
        max_async_actions: int = 10,
        backend_type: BackendType = "kafka",
        backend_config: KafkaConfig | InMemoryConfig | None = None,
    ):
        _ = max_async_actions
        super().__init__(
            model=DataToPredictStruct,
            topic="data.to_predict",
            partition_key_fn=lambda message: str(message.player_id % 10),
            bootstrap_servers=bootstrap_servers,
            backend_type=backend_type,
            backend_config=backend_config,
        )


class DataToPredictConsumer(_BaseConsumerFacade[DataToPredictStruct]):
    def __init__(
        self,
        group_id: str,
        bootstrap_servers: str | None,
        enable_auto_commit: bool = True,
        backend_type: BackendType = "kafka",
        backend_config: KafkaConfig | InMemoryConfig | None = None,
    ):
        super().__init__(
            model=DataToPredictStruct,
            topic="data.to_predict",
            group_id=group_id,
            bootstrap_servers=bootstrap_servers,
            enable_auto_commit=enable_auto_commit,
            backend_type=backend_type,
            backend_config=backend_config,
        )


class DataToPredictQueue(_BaseQueueFacade[DataToPredictStruct]):
    def __init__(
        self,
        group_id: str,
        bootstrap_servers: str | None,
        enable_auto_commit: bool = True,
        backend_type: BackendType = "kafka",
        backend_config: KafkaConfig | InMemoryConfig | None = None,
    ):
        super().__init__(
            model=DataToPredictStruct,
            topic="data.to_predict",
            partition_key_fn=lambda message: str(message.player_id % 10),
            group_id=group_id,
            bootstrap_servers=bootstrap_servers,
            enable_auto_commit=enable_auto_commit,
            backend_type=backend_type,
            backend_config=backend_config,
        )


__all__ = [
    "Settings",
    "ToScrapeStruct",
    "ScrapedStruct",
    "NotFoundStruct",
    "ReportsToInsertStruct",
    "HighScoreStruct",
    "DataToPredictStruct",
    "PlayersToScrapeProducer",
    "PlayersToScrapeConsumer",
    "PlayersToScrapeQueue",
    "PlayersScrapedProducer",
    "PlayersScrapedConsumer",
    "PlayersScrapedQueue",
    "PlayersNotFoundProducer",
    "PlayersNotFoundConsumer",
    "PlayersNotFoundQueue",
    "ReportsToInsertProducer",
    "ReportsToInsertConsumer",
    "ReportsToInsertQueue",
    "DataToPredictProducer",
    "DataToPredictConsumer",
    "DataToPredictQueue",
]
