import logging

from bot_detector.database.report import ReportRepo
from bot_detector.event_queue.structs import ReportsToInsertStruct
from bot_detector.structs import ParsedDetection
from bot_detector.worker.core import Worker
from bot_detector.worker_report.adapter import transform_report
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


async def insert_batch(
    report_repo: ReportRepo,
    batch: list[ParsedDetection],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    logger.debug(f"batch inserting: {len(batch)}")
    try:
        async with session_factory() as session, session.begin():
            await report_repo.insert(async_session=session, reports=batch)
    except OperationalError as e:
        logger.error(f"OperationalError during batch insert: {e}")
        raise
    logger.info(f"inserted: {len(batch)}")


class ReportWorker(Worker[ReportsToInsertStruct]):
    def __init__(
        self,
        worker_id: int,
        session_factory: async_sessionmaker[AsyncSession],
        report_repo: ReportRepo,
    ) -> None:
        self._id = worker_id
        self._session_factory = session_factory
        self._report_repo = report_repo

    async def handle(
        self, batch: list[ReportsToInsertStruct]
    ) -> list[ReportsToInsertStruct]:
        logger.info(f"[{self._id}] consumed {len(batch)} reports")
        parsed = [
            r for r in (transform_report(record) for record in batch) if r is not None
        ]
        if not parsed:
            logger.info("No valid reports to process.")
            return []
        await insert_batch(
            report_repo=self._report_repo,
            batch=parsed,
            session_factory=self._session_factory,
        )
        logger.info(f"[{self._id}] processed {len(parsed)} reports")
        return []
