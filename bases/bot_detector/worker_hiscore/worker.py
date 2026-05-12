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
    ScrapedStruct,
)
from bot_detector.worker.core import Worker, WorkerRunner
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from . import adapter
from .settings import Settings

logger = logging.getLogger(__name__)


async def insert_batch(
    session_factory: async_sessionmaker[AsyncSession],
    batch: list[ScrapedStruct],
    highscore_repo: HighscoreDataRepo,
    player_repo: PlayerRepo,
) -> None:
    logger.debug(f"batch inserting: {len(batch)}")
    # extract player and highscore data
    player_batch = [d.player_data for d in batch]
    highscore_batch = [d.highscore_data for d in batch if d.highscore_data is not None]

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
    logger.debug(f"inserted: {len(batch)}")


class HiscoreWorker(Worker[ScrapedStruct]):
    def __init__(
        self,
        worker_id: int,
        session_factory: async_sessionmaker[AsyncSession],
        player_repo: PlayerRepo,
        highscore_repo: HighscoreDataRepo,
        data_to_predict_producer: QueueProducer[DataToPredictStruct],
    ) -> None:
        self._id = worker_id
        self._session_factory = session_factory
        self._player_repo = player_repo
        self._highscore_repo = highscore_repo
        self._data_to_predict_producer = data_to_predict_producer

    async def handle(self, batch: list[ScrapedStruct]) -> None:
        """
        insert batch into DB, then produce to "players.to_predict" topic for records with highscore data.
        when there is an error the Worker logic will reinsert the batch into the queue.
        """
        logger.info(f"[{self._id}] consumed {len(batch)} scrapes")

        await insert_batch(
            session_factory=self._session_factory,
            highscore_repo=self._highscore_repo,
            player_repo=self._player_repo,
            batch=batch,
        )

        to_predict_batch = [adapter.transform_scraped_struct(r) for r in batch]
        to_predict_batch = [d for d in to_predict_batch if d is not None]
        await self._data_to_predict_producer.put(to_predict_batch)
        logger.info(f"[{self._id}] processed {len(to_predict_batch)} scrapes")


async def main():
    SETTINGS = Settings()
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
            producer_config=KafkaProducerConfig(partition_key_fn=partition_key_fn),
        ),
    )
    if isinstance(data_to_predict_producer, Exception):
        raise data_to_predict_producer
    assert isinstance(data_to_predict_producer, QueueProducer)
    await data_to_predict_producer.start()

    tasks = []
    for worker_id in range(SETTINGS.N_WORKERS):
        worker = HiscoreWorker(
            worker_id=worker_id,
            session_factory=session_factory,
            highscore_repo=highscore_repo,
            player_repo=player_repo,
            data_to_predict_producer=data_to_predict_producer,
        )
        kafka_config = KafkaConfig(
            topic="players.scraped",
            bootstrap_servers=KafkaSettings().bootstrap_servers,
            producer=True,
            consumer=True,
            producer_config=KafkaProducerConfig(partition_key_fn=partition_key_fn),
            consumer_config=KafkaConsumerConfig(group_id="highscore_worker"),
        )
        runner = WorkerRunner(
            config=kafka_config,
            model=ScrapedStruct,
            worker=worker,
            batch_size=SETTINGS.MAX_BATCH_SIZE,
        )
        task = asyncio.create_task(runner.run())
        tasks.append(task)

    await asyncio.gather(*tasks)
    await async_engine.dispose()


async def run_async():
    await main()


def run():
    asyncio.run(run_async())


if __name__ == "__main__":
    run()
