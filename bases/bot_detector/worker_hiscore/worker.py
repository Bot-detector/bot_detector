import logging

from bot_detector.database.hiscore import HighscoreDataRepo
from bot_detector.database.player import PlayerRepo
from bot_detector.event_queue.core import QueueProducer
from bot_detector.event_queue.structs import (
    DataToPredictStruct,
    ScrapedStruct,
)
from bot_detector.worker.core import Worker
from bot_detector.worker_hiscore import adapter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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

    async with session_factory() as session, session.begin():
        await player_repo.update_many_players(
            async_session=session,
            players_data=player_batch,
        )
        await highscore_repo.insert_highscore_many(
            async_session=session,
            highscore_data=highscore_batch,
        )
            # session.begin() context manager will commit if no exceptions, rollback if exception occurs
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

    async def handle(self, batch: list[ScrapedStruct]) -> list[ScrapedStruct]:
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
        return []
