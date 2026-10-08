import logging

from bot_detector.database.prediction import PredictionLatestRepo, PredictionRepo
from bot_detector.event_queue.structs import PredictionsToInsertStruct
from bot_detector.worker.core import Worker
from bot_detector.worker_prediction.metrics import predictions_inserted_counter
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


async def insert_batch(
    prediction_repo: PredictionRepo,
    prediction_latest_repo: PredictionLatestRepo,
    batch: list[PredictionsToInsertStruct],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    logger.debug(f"batch inserting: {len(batch)}")
    try:
        async with session_factory() as session:
            await prediction_repo.insert(async_session=session, predictions=batch)
            await prediction_latest_repo.insert(
                async_session=session,
                predictions=batch,
            )
    except OperationalError as e:
        logger.error(f"OperationalError during batch insert: {e}")
        raise
    predictions_inserted_counter.inc(len(batch))
    logger.info(f"inserted: {len(batch)}")


class PredictionWorker(Worker[PredictionsToInsertStruct]):
    def __init__(
        self,
        worker_id: int,
        session_factory: async_sessionmaker[AsyncSession],
        prediction_repo: PredictionRepo,
        prediction_latest_repo: PredictionLatestRepo,
    ) -> None:
        self._id = worker_id
        self._session_factory = session_factory
        self._prediction_repo = prediction_repo
        self._prediction_latest_repo = prediction_latest_repo

    async def handle(
        self, batch: list[PredictionsToInsertStruct]
    ) -> list[PredictionsToInsertStruct]:
        logger.info(f"[{self._id}] consumed {len(batch)} predictions")
        if not batch:
            logger.info("No predictions to process.")
            return []
        await insert_batch(
            prediction_repo=self._prediction_repo,
            prediction_latest_repo=self._prediction_latest_repo,
            batch=batch,
            session_factory=self._session_factory,
        )
        logger.info(f"[{self._id}] processed {len(batch)} predictions")
        return []
