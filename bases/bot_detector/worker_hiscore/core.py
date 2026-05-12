import asyncio
import logging

from bot_detector import database as db
from bot_detector.database import Settings as DBSettings
from bot_detector.database.hiscore import HighscoreDataRepo
from bot_detector.database.player import PlayerRepo
from bot_detector.event_queue.adapters.kafka import (
    KafkaConfig,
    KafkaConsumerConfig,
    KafkaProducerConfig,
    KafkaSettings,
)
from bot_detector.event_queue.core import QueueProducer
from bot_detector.event_queue.factory import QueueFactory
from bot_detector.event_queue.structs import (
    DataToPredictStruct,
    HighScoreStruct,
    ScrapedStruct,
)
from bot_detector.worker import Worker, WorkerRunner
from pydantic import ValidationError
from pydantic_settings import BaseSettings
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    N_WORKERS: int = 1
    MAX_BATCH_SIZE: int = 10_000
    MAX_INTERVAL_MS: int = 5_000


async def insert_batch(
    session_factory: async_sessionmaker[AsyncSession],
    batch: list[ScrapedStruct],
    highscore_repo: HighscoreDataRepo,
    player_repo: PlayerRepo,
) -> tuple[None, str | None]:
    logger.debug(f"batch inserting: {len(batch)}")
    player_batch = [d.player_data for d in batch]
    highscore_batch = [d.highscore_data for d in batch if d.highscore_data is not None]

    try:
        async with session_factory() as session:
            async with session.begin():
                await player_repo.update_many_players(
                    async_session=session,
                    players_data=player_batch,
                )
                await highscore_repo.insert_highscore_many(
                    async_session=session,
                    highscore_data=highscore_batch,
                )
                await session.commit()
    except OperationalError as e:
        return None, str(e)

    logger.debug(f"inserted: {len(batch)}")
    return None, None


def transform_scraped_struct(
    record: ScrapedStruct,
) -> DataToPredictStruct | None:
    if record.highscore_data is None:
        logger.debug("Highscore data is None")
        return None

    _player_id = record.player_data.id
    _skills = record.highscore_data.skills or {}
    _skills = {k.lower(): v for k, v in _skills.items() if v is not None}
    _activities = record.highscore_data.activities or {}
    _activities = {k.lower(): v for k, v in _activities.items() if v is not None}
    try:
        _data = HighScoreStruct.model_validate(_skills | _activities)
    except ValidationError as e:
        logger.error(
            "Failed to validate HighScoreStruct",
            extra={
                "player_id": _player_id,
                "data": _skills | _activities,
                "errors": e.errors(),
            },
            exc_info=True,
        )
        return None
    try:
        _data_to_predict = DataToPredictStruct.model_validate(
            {
                "player_id": _player_id,
                "data": _data,
            }
        )
        return _data_to_predict
    except ValidationError as e:
        logger.error(
            "Failed to validate DataToPredictStruct",
            extra={
                "player_id": _player_id,
                "data": _skills | _activities,
                "errors": e.errors(),
            },
            exc_info=True,
        )
        return None


async def produce_data_to_predict(
    data_to_predict_producer: QueueProducer[DataToPredictStruct],
    batch: list[ScrapedStruct],
):
    _tasks = []
    for _record in batch:
        _data_to_predict = transform_scraped_struct(_record)
        if _data_to_predict is None:
            continue
        _tasks.append(data_to_predict_producer.put([_data_to_predict]))

    produce_results = await asyncio.gather(*_tasks)
    for produce_result in produce_results:
        if isinstance(produce_result, Exception):
            logger.error(f"Failed to produce data_to_predict message: {produce_result}")

    logger.info(f"Produced {len(_tasks)} messages to data to predict topic.")


class HiscoreWorker(Worker[ScrapedStruct]):
    def __init__(
        self,
        worker_id: int,
        session_factory: async_sessionmaker[AsyncSession],
        highscore_repo: HighscoreDataRepo,
        player_repo: PlayerRepo,
        data_to_predict_producer: QueueProducer[DataToPredictStruct],
    ) -> None:
        self._worker_id = worker_id
        self._session_factory = session_factory
        self._highscore_repo = highscore_repo
        self._player_repo = player_repo
        self._data_to_predict_producer = data_to_predict_producer

    async def handle(self, batch: list[ScrapedStruct]) -> None:
        logger.info(f"[{self._worker_id}] consumed {len(batch)} scrapes")

        _, error = await insert_batch(
            highscore_repo=self._highscore_repo,
            player_repo=self._player_repo,
            batch=batch,
            session_factory=self._session_factory,
        )

        await produce_data_to_predict(
            data_to_predict_producer=self._data_to_predict_producer,
            batch=batch,
        )

        if error:
            raise RuntimeError(error)


async def main():
    session_factory, async_engine = db.get_session_factory(SETTINGS=DBSettings())

    player_repo = PlayerRepo()
    highscore_repo = HighscoreDataRepo()

    def partition_key_fn(msg: ScrapedStruct) -> str:
        return str(msg.player_data.id % 10)

    data_to_predict_producer = QueueFactory.create_queue(
        model=DataToPredictStruct,
        queue_type="producer",
        backend_type="kafka",
        config=KafkaConfig(
            topic="data.to_predict",
            bootstrap_servers=KafkaSettings().bootstrap_servers,
            producer=True,
            producer_config=KafkaProducerConfig(partition_key_fn=None),
        ),
    )
    if isinstance(data_to_predict_producer, Exception):
        raise data_to_predict_producer
    assert isinstance(data_to_predict_producer, QueueProducer)

    await data_to_predict_producer.start()

    settings = Settings()

    runners = []
    for worker_id in range(settings.N_WORKERS):
        worker = HiscoreWorker(
            worker_id=worker_id,
            session_factory=session_factory,
            highscore_repo=highscore_repo,
            player_repo=player_repo,
            data_to_predict_producer=data_to_predict_producer,
        )
        runner = WorkerRunner(
            config=KafkaConfig(
                topic="players.scraped",
                bootstrap_servers=KafkaSettings().bootstrap_servers,
                producer=True,
                consumer=True,
                producer_config=KafkaProducerConfig(partition_key_fn=partition_key_fn),
                consumer_config=KafkaConsumerConfig(group_id="highscore_worker"),
            ),
            model=ScrapedStruct,
            worker=worker,
            batch_size=settings.MAX_BATCH_SIZE,
            empty_batch_sleep=15.0,
            error_sleep=15.0,
        )
        runners.append(asyncio.create_task(runner.run()))

    await asyncio.gather(*runners)
    await data_to_predict_producer.stop()
    await async_engine.dispose()


async def run_async():
    await main()


def run():
    asyncio.run(run_async())


if __name__ == "__main__":
    run()
