import asyncio
import logging

from bot_detector.database import Settings as DBSettings
from bot_detector.database import get_session_factory
from bot_detector.database.report import prune_reports
from bot_detector.job_prune_reports.metrics import (
    rows_deleted_counter,
    start_metrics_server,
)
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    REPORT_RETENTION_DAYS: int = 90
    BATCH_SIZE: int = 10_000
    METRICS_PORT: int = 8000


async def main():
    start_metrics_server(port=Settings().METRICS_PORT)
    session_factory, async_engine = get_session_factory(SETTINGS=DBSettings())
    settings = Settings()
    try:
        deleted = await prune_reports(
            session_factory=session_factory,
            older_than_days=settings.REPORT_RETENTION_DAYS,
            batch_size=settings.BATCH_SIZE,
        )
        if deleted is not None:
            rows_deleted_counter.inc(deleted)
        logger.info(f"Pruned {deleted} report rows")
    finally:
        await async_engine.dispose()


async def run_async():
    await main()


def run():
    asyncio.run(run_async())


if __name__ == "__main__":
    run()
