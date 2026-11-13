import asyncio
import logging

from bot_detector.database import Settings as DBSettings
from bot_detector.database import get_session_factory
from bot_detector.database.report import prune_reports
from bot_detector.job_prune_reports.metrics import (
    rows_deleted_counter,
    start_metrics_server,
)
from pydantic import Field
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    REPORT_RETENTION_DAYS: int = 90
    BATCH_SIZE: int = Field(default=10_000, gt=0)
    METRICS_PORT: int = 8000


async def main():
    settings = Settings()
    try:
        start_metrics_server(port=settings.METRICS_PORT)
    except OSError as e:
        logger.warning({"msg": "metrics server failed to start", "error": str(e)})
    session_factory, async_engine = get_session_factory(SETTINGS=DBSettings())
    try:
        deleted = await prune_reports(
            session_factory=session_factory,
            older_than_days=settings.REPORT_RETENTION_DAYS,
            batch_size=settings.BATCH_SIZE,
        )
        rows_deleted_counter.inc(deleted)
        logger.info(f"Pruned {deleted} report rows")
    finally:
        await async_engine.dispose()


async def run_async():
    await main()


def run():
    try:
        asyncio.run(run_async())
    except Exception:
        logger.exception("job_prune_reports failed")
        raise SystemExit(1)


if __name__ == "__main__":
    run()
