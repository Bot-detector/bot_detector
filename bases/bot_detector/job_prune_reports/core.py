import asyncio
import logging

from bot_detector.database import Settings as DBSettings
from bot_detector.database import get_session_factory
from bot_detector.database.report import prune_reports
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    REPORT_RETENTION_DAYS: int = 90
    BATCH_SIZE: int = 10_000


async def main():
    session_factory, async_engine = get_session_factory(SETTINGS=DBSettings())
    settings = Settings()
    try:
        deleted = await prune_reports(
            session_factory=session_factory,
            older_than_days=settings.REPORT_RETENTION_DAYS,
            batch_size=settings.BATCH_SIZE,
        )
        logger.info(f"Pruned {deleted} report rows")
    finally:
        await async_engine.dispose()


async def run_async():
    await main()


def run():
    asyncio.run(run_async())


if __name__ == "__main__":
    run()
