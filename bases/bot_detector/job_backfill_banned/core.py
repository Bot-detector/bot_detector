import asyncio
import logging

import sqlalchemy as sqla
from bot_detector.database import Settings as DBSettings
from bot_detector.database import get_session_factory
from bot_detector.database.report import migrate_banned_player_reports
from pydantic_settings import BaseSettings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    BATCH_SIZE: int = 10_000


def _select_banned_player_ids() -> sqla.TextClause:
    """Page through Players flagged as Jagex-banned (label_jagex = 2)."""
    return sqla.text(
        """
        SELECT id FROM Players
        WHERE label_jagex = 2 AND id > :player_id
        ORDER BY id ASC
        LIMIT :limit
        """
    )


async def backfill(
    session_factory: async_sessionmaker[AsyncSession],
    batch_size: int = 10_000,
) -> int:
    """Archive location history for every Jagex-banned player.

    Paginates Players where label_jagex = 2 and runs the migration function per
    player. Each player is migrated in its own transaction; a failure for one
    player is logged and skipped so the backfill can complete. Idempotent:
    INSERT IGNORE makes a re-run safe if the one-time execution is interrupted.

    Args:
        session_factory: SQLAlchemy async session factory.
        batch_size: Number of player ids fetched per page.

    Returns:
        Number of banned players processed.
    """
    sql = _select_banned_player_ids()
    player_id = 0
    processed = 0

    while True:
        async with session_factory() as session:
            result = await session.execute(
                sql,
                params={"player_id": player_id, "limit": batch_size},
            )
            ids = [row for row in result.scalars().all()]

        if not ids:
            logger.info("backfill: no more banned players, exiting")
            break

        for reported_id in ids:
            try:
                await migrate_banned_player_reports(
                    session_factory=session_factory,
                    reported_id=reported_id,
                )
                processed += 1
            except Exception as e:
                logger.error(
                    f"backfill: failed to archive reported_id={reported_id}: {e}"
                )

        player_id = ids[-1]
        logger.info(
            f"backfill: processed up to player_id={player_id} ({processed} total)"
        )

    logger.info(f"backfill: finished, {processed} banned players processed")
    return processed


async def main():
    session_factory, async_engine = get_session_factory(SETTINGS=DBSettings())
    settings = Settings()
    try:
        await backfill(
            session_factory=session_factory,
            batch_size=settings.BATCH_SIZE,
        )
    finally:
        await async_engine.dispose()


async def run_async():
    await main()


def run():
    asyncio.run(run_async())


if __name__ == "__main__":
    run()
