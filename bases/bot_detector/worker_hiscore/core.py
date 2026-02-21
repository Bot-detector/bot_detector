import asyncio
import logging
import traceback

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
from bot_detector.event_queue.core import Queue, QueueProducer
from bot_detector.event_queue.factory import QueueFactory
from bot_detector.event_queue.structs import (
    DataToPredictStruct,
    HighScoreStruct,
    ScrapedStruct,
)
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
    # extract player and highscore data
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


async def consume_many_task(
    worker_id: int,
    max_messages: int,
    player_sc_queue: Queue[ScrapedStruct],
    data_to_predict_producer: QueueProducer[DataToPredictStruct],
    highscore_repo: HighscoreDataRepo,
    player_repo: PlayerRepo,
    session_factory: async_sessionmaker[AsyncSession],
):
    while True:
        batch: list[ScrapedStruct] = []
        try:
            consume_result = await player_sc_queue.get_many(count=max_messages)
            if isinstance(consume_result, Exception):
                logger.error(
                    f"[{worker_id}] Error during consumption: {consume_result}"
                )
                await asyncio.sleep(15)
                continue

            batch = consume_result
            logger.info(f"[{worker_id}] consumed {len(batch)} scrapes")

            if not batch:
                logger.info("No highscore data to process.")
                await asyncio.sleep(15)
                continue

            _, error = await insert_batch(
                highscore_repo=highscore_repo,
                player_repo=player_repo,
                batch=batch,
                session_factory=session_factory,
            )

            await produce_data_to_predict(
                data_to_predict_producer=data_to_predict_producer,
                batch=batch,
            )

            if error:
                logger.error(f"{error}")
                requeue_results = await asyncio.gather(
                    *[player_sc_queue.put([b]) for b in batch]
                )
                for requeue_result in requeue_results:
                    if isinstance(requeue_result, Exception):
                        logger.error(
                            f"Failed to requeue scraped message: {requeue_result}"
                        )
                await asyncio.sleep(15)

            await player_sc_queue.commit()

            # ideally we want batches to be as full as possible, this is more efficient on the database
            if len(batch) < 1000:
                await asyncio.sleep(60)
        except Exception as e:
            logger.error(f"[{worker_id}] Error consuming scrapes: {e}")
            logger.debug(f"[{worker_id}] Traceback: \n{traceback.format_exc()}")
            if batch:  # only retry if we have data
                requeue_results = await asyncio.gather(
                    *[player_sc_queue.put([b]) for b in batch]
                )
                for requeue_result in requeue_results:
                    if isinstance(requeue_result, Exception):
                        logger.error(
                            f"Failed to requeue scraped message: {requeue_result}"
                        )
            await asyncio.sleep(15)


async def main():
    session_factory, async_engine = db.get_session_factory(SETTINGS=DBSettings())

    player_repo = PlayerRepo()
    highscore_repo = HighscoreDataRepo()

    def partition_key_fn(msg: ScrapedStruct) -> str:
        return str(msg.player_data.id % 10)

    ## queue
    player_sc_queue = QueueFactory.create_queue(
        model=ScrapedStruct,
        queue_type="queue",
        backend_type="kafka",
        config=KafkaConfig(
            topic="players.scraped",
            bootstrap_servers=KafkaSettings().bootstrap_servers,
            producer=True,
            consumer=True,
            producer_config=KafkaProducerConfig(partition_key_fn=partition_key_fn),
            consumer_config=KafkaConsumerConfig(group_id="highscore_worker"),
        ),
    )
    assert isinstance(player_sc_queue, Queue)

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

    await player_sc_queue.start()
    await data_to_predict_producer.start()

    # start workers
    workers = [
        asyncio.create_task(
            consume_many_task(
                worker_id=worker_id,
                max_messages=Settings().MAX_BATCH_SIZE,
                player_sc_queue=player_sc_queue,
                data_to_predict_producer=data_to_predict_producer,
                highscore_repo=highscore_repo,
                player_repo=player_repo,
                session_factory=session_factory,
            )
        )
        for worker_id in range(Settings().N_WORKERS)
    ]
    await asyncio.gather(*workers)
    await async_engine.dispose()


async def run_async():
    await main()


def run():
    asyncio.run(run_async())


if __name__ == "__main__":
    run()
