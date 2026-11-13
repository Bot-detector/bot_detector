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
    # gt=0: batch_size 0 makes prune_reports loop forever on no-op deletes
    BATCH_SIZE: int = Field(default=10_000, gt=0)
    METRICS_PORT: int = 8000


async def main():
    settings = Settings()
    try:
        start_metrics_server(port=settings.METRICS_PORT)
    except OSError as e:
        # metrics are auxiliary; a port conflict must not stop the prune
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
        # boundary handler: get the crash into the JSON log pipeline, then exit nonzero
        logger.exception("job_prune_reports failed")
        raise SystemExit(1)


if __name__ == "__main__":
    run()
