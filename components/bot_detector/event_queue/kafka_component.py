from typing import Generic, TypeVar, cast

from bot_detector.event_queue.adapters.kafka import (
    KafkaConfig,
    KafkaConsumerConfig,
    KafkaProducerConfig,
)
from bot_detector.event_queue.core import QueueConsumer, QueueProducer
from bot_detector.event_queue.factory import QueueFactory
from bot_detector.structs._metadata import MetaData
from bot_detector.structs.hiscore import HighscoreBaseStruct
from bot_detector.structs.player import PlayerStruct
from bot_detector.structs.reports import ParsedDetection
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

T = TypeVar("T", bound=BaseModel)


class Settings(BaseSettings):
    KAFKA_BOOTSTRAP_SERVERS: str = Field(default=...)


class ToScrapeStruct(BaseModel):
    metadata: MetaData
    player_data: PlayerStruct


class ScrapedStruct(BaseModel):
    metadata: MetaData
    player_data: PlayerStruct
    highscore_data: HighscoreBaseStruct | None


class NotFoundStruct(BaseModel):
    metadata: MetaData
    player_data: PlayerStruct


class ReportsToInsertStruct(BaseModel):
    metadata: MetaData
    report: ParsedDetection


class HighScoreStruct(BaseModel):
    attack: int = 0
    defence: int = 0
    strength: int = 0
    hitpoints: int = 0
    ranged: int = 0
    prayer: int = 0
    magic: int = 0
    cooking: int = 0
    woodcutting: int = 0
    fletching: int = 0
    fishing: int = 0
    firemaking: int = 0
    crafting: int = 0
    smithing: int = 0
    mining: int = 0
    herblore: int = 0
    agility: int = 0
    thieving: int = 0
    slayer: int = 0
    farming: int = 0
    runecraft: int = 0
    hunter: int = 0
    construction: int = 0
    lms_rank: int = 0
    soul_wars_zeal: int = 0
    cs_all: int = 0
    cs_beginner: int = 0
    cs_easy: int = 0
    cs_medium: int = 0
    cs_hard: int = 0
    cs_elite: int = 0
    cs_master: int = 0
    abyssal_sire: int = 0
    alchemical_hydra: int = 0
    barrows_chests: int = 0
    bryophyta: int = 0
    callisto: int = 0
    cerberus: int = 0
    chambers_of_xeric: int = 0
    chambers_of_xeric_challenge_mode: int = 0
    chaos_elemental: int = 0
    chaos_fanatic: int = 0
    commander_zilyana: int = 0
    corporeal_beast: int = 0
    crazy_archaeologist: int = 0
    dagannoth_prime: int = 0
    dagannoth_rex: int = 0
    dagannoth_supreme: int = 0
    deranged_archaeologist: int = 0
    general_graardor: int = 0
    giant_mole: int = 0
    grotesque_guardians: int = 0
    hespori: int = 0
    kalphite_queen: int = 0
    king_black_dragon: int = 0
    kraken: int = 0
    kreearra: int = 0
    kril_tsutsaroth: int = 0
    mimic: int = 0
    nex: int = 0
    nightmare: int = 0
    phosanis_nightmare: int = 0
    obor: int = 0
    sarachnis: int = 0
    scorpia: int = 0
    skotizo: int = 0
    tempoross: int = 0
    the_gauntlet: int = 0
    the_corrupted_gauntlet: int = 0
    theatre_of_blood: int = 0
    theatre_of_blood_hard: int = 0
    thermonuclear_smoke_devil: int = 0
    tombs_of_amascut: int = 0
    tombs_of_amascut_expert: int = 0
    tzkal_zuk: int = 0
    tztok_jad: int = 0
    venenatis: int = 0
    vetion: int = 0
    vorkath: int = 0
    wintertodt: int = 0
    zalcano: int = 0
    zulrah: int = 0


class DataToPredictStruct(BaseModel):
    player_id: int
    data: HighScoreStruct


def _create_producer(
    model: type[T],
    topic: str,
    bootstrap_servers: str,
    partition_key_fn,
) -> QueueProducer[T]:
    queue = QueueFactory.create_queue(
        model=model,
        queue_type="producer",
        backend_type="kafka",
        config=KafkaConfig(
            topic=topic,
            bootstrap_servers=bootstrap_servers,
            producer=True,
            consumer=False,
            producer_config=KafkaProducerConfig(partition_key_fn=partition_key_fn),
            consumer_config=None,
        ),
    )
    if isinstance(queue, Exception):
        raise queue
    return cast(QueueProducer[T], queue)


def _create_consumer(
    model: type[T],
    topic: str,
    group_id: str,
    bootstrap_servers: str,
    enable_auto_commit: bool,
    timeout_ms: int,
) -> tuple[QueueConsumer[T], KafkaConfig]:
    config = KafkaConfig(
        topic=topic,
        bootstrap_servers=bootstrap_servers,
        producer=False,
        consumer=True,
        producer_config=None,
        consumer_config=KafkaConsumerConfig(
            group_id=group_id,
            enable_auto_commit=enable_auto_commit,
            consume_timeout_ms=timeout_ms,
        ),
    )
    queue = QueueFactory.create_queue(
        model=model,
        queue_type="consumer",
        backend_type="kafka",
        config=config,
    )
    if isinstance(queue, Exception):
        raise queue
    return cast(QueueConsumer[T], queue), config


class BaseQueueProducer(Generic[T]):
    def __init__(
        self,
        model: type[T],
        topic: str,
        bootstrap_servers: str,
        partition_key_fn,
    ):
        self._producer = _create_producer(
            model=model,
            topic=topic,
            bootstrap_servers=bootstrap_servers,
            partition_key_fn=partition_key_fn,
        )

    async def start(self):
        await self._producer.start()

    async def stop(self):
        await self._producer.stop()

    async def produce_one(self, message: T, topic: str | None = None, **_kwargs):
        _ = topic
        await self._producer.put([message])


class BaseQueueConsumer(Generic[T]):
    def __init__(
        self,
        model: type[T],
        topic: str,
        group_id: str,
        bootstrap_servers: str,
        enable_auto_commit: bool = True,
    ):
        self._consumer, self._consumer_config = _create_consumer(
            model=model,
            topic=topic,
            group_id=group_id,
            bootstrap_servers=bootstrap_servers,
            enable_auto_commit=enable_auto_commit,
            timeout_ms=5_000,
        )

    async def start(self):
        await self._consumer.start()

    async def stop(self):
        await self._consumer.stop()

    async def consume_many(self, max_records: int, timeout_ms: int):
        self._consumer_config.consumer_config.consume_timeout_ms = timeout_ms
        result = await self._consumer.get_many(count=max_records)
        if isinstance(result, Exception):
            return [], [str(result)]
        return result, []

    async def commit(self):
        error = await self._consumer.commit()
        if isinstance(error, Exception):
            raise error


class PlayersToScrapeProducer(BaseQueueProducer[ToScrapeStruct]):
    def __init__(self, bootstrap_servers: str, max_async_actions: int = 10):
        _ = max_async_actions
        super().__init__(
            ToScrapeStruct,
            "players.to_scrape",
            bootstrap_servers,
            partition_key_fn=lambda message: str(message.player_data.id % 10),
        )


class PlayersToScrapeConsumer(BaseQueueConsumer[ToScrapeStruct]):
    def __init__(
        self, group_id: str, bootstrap_servers: str, enable_auto_commit: bool = True
    ):
        super().__init__(
            ToScrapeStruct,
            "players.to_scrape",
            group_id,
            bootstrap_servers,
            enable_auto_commit,
        )


class PlayersScrapedProducer(BaseQueueProducer[ScrapedStruct]):
    def __init__(self, bootstrap_servers: str, max_async_actions: int = 10):
        _ = max_async_actions
        super().__init__(
            ScrapedStruct,
            "players.scraped",
            bootstrap_servers,
            partition_key_fn=lambda message: str(message.player_data.id % 10),
        )


class PlayersScrapedConsumer(BaseQueueConsumer[ScrapedStruct]):
    def __init__(
        self, group_id: str, bootstrap_servers: str, enable_auto_commit: bool = True
    ):
        super().__init__(
            ScrapedStruct,
            "players.scraped",
            group_id,
            bootstrap_servers,
            enable_auto_commit,
        )


class PlayersNotFoundProducer(BaseQueueProducer[NotFoundStruct]):
    def __init__(self, bootstrap_servers: str, max_async_actions: int = 10):
        _ = max_async_actions
        super().__init__(
            NotFoundStruct,
            "players.not_found",
            bootstrap_servers,
            partition_key_fn=lambda message: str(message.player_data.id % 10),
        )


class PlayersNotFoundConsumer(BaseQueueConsumer[NotFoundStruct]):
    def __init__(
        self, group_id: str, bootstrap_servers: str, enable_auto_commit: bool = True
    ):
        super().__init__(
            NotFoundStruct,
            "players.not_found",
            group_id,
            bootstrap_servers,
            enable_auto_commit,
        )


class ReportsToInsertProducer(BaseQueueProducer[ReportsToInsertStruct]):
    def __init__(self, bootstrap_servers: str, max_async_actions: int = 10):
        _ = max_async_actions
        super().__init__(
            ReportsToInsertStruct,
            "reports.to_insert",
            bootstrap_servers,
            partition_key_fn=lambda message: str(message.report.reported_ts),
        )


class ReportsToInsertConsumer(BaseQueueConsumer[ReportsToInsertStruct]):
    def __init__(
        self, group_id: str, bootstrap_servers: str, enable_auto_commit: bool = True
    ):
        super().__init__(
            ReportsToInsertStruct,
            "reports.to_insert",
            group_id,
            bootstrap_servers,
            enable_auto_commit,
        )


class DataToPredictProducer(BaseQueueProducer[DataToPredictStruct]):
    def __init__(self, bootstrap_servers: str, max_async_actions: int = 10):
        _ = max_async_actions
        super().__init__(
            DataToPredictStruct,
            "data.to_predict",
            bootstrap_servers,
            partition_key_fn=lambda message: str(message.player_id % 10),
        )


class DataToPredictConsumer(BaseQueueConsumer[DataToPredictStruct]):
    def __init__(
        self, group_id: str, bootstrap_servers: str, enable_auto_commit: bool = True
    ):
        super().__init__(
            DataToPredictStruct,
            "data.to_predict",
            group_id,
            bootstrap_servers,
            enable_auto_commit,
        )
