import asyncio
import logging

import sqlalchemy as sqla
from bot_detector.database import Settings as DBSettings
from bot_detector.database import get_session_factory
from bot_detector.database.report import migrate_banned_player_reports
from bot_detector.event_queue.adapters.kafka import KafkaLagProbe, KafkaSettings
from bot_detector.event_queue.lag_probe import LagProbeProtocol
from pydantic_settings import BaseSettings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    BATCH_SIZE: int = 10_000
    MAX_LAG: int = 100_000
    LAG_SLEEP_SECONDS: int = 10


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
    lag_probe: LagProbeProtocol,
    lag_topic: str,
    lag_group_id: str,
    batch_size: int = 10_000,
    max_lag: int = 100_000,
    lag_sleep_seconds: int = 10,
) -> int:
    """Archive location history for every Jagex-banned player.

    Paginates Players where label_jagex = 2 and runs the migration function per
    player. Each player is migrated in its own transaction; a failure for one
    player is logged and skipped so the backfill can complete. Idempotent:
    INSERT IGNORE makes a re-run safe if the one-time execution is interrupted.

    Before each page, checks consumer lag on the players.banned topic for the
    ban_migration_worker group. If lag >= max_lag the run sleeps and retries,
    so the backfill cannot outrun the live worker and pile load onto
    report_archive while it is catching up.

    Args:
        session_factory: SQLAlchemy async session factory.
        lag_probe: Kafka lag probe used to throttle against the live worker.
        lag_topic: Topic whose lag gates the run (players.banned).
        lag_group_id: Consumer group whose lag gates the run.
        batch_size: Number of player ids fetched per page.
        max_lag: Lag threshold above which the run throttles.
        lag_sleep_seconds: Sleep duration when throttled.

    Returns:
        Number of banned players processed.
    """
    sql = _select_banned_player_ids()
    player_id = 0
    processed = 0

    while True:
        lag = await lag_probe.lag(topic=lag_topic, group_id=lag_group_id)
        if lag >= max_lag:
            logger.info(
                f"backfill: lag_throttle lag={lag} >= max_lag={max_lag}, "
                f"sleeping {lag_sleep_seconds}s"
            )
            await asyncio.sleep(lag_sleep_seconds)
            continue

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

    bootstrap_servers = KafkaSettings().bootstrap_servers
    lag_topic = "players.banned"
    lag_group_id = "ban_migration_worker"

    lag_probe = KafkaLagProbe(bootstrap_servers)
    if isinstance(lag_probe, Exception):
        raise lag_probe

    await lag_probe.start()
    try:
        await backfill(
            session_factory=session_factory,
            lag_probe=lag_probe,
            lag_topic=lag_topic,
            lag_group_id=lag_group_id,
            batch_size=settings.BATCH_SIZE,
            max_lag=settings.MAX_LAG,
            lag_sleep_seconds=settings.LAG_SLEEP_SECONDS,
        )
    finally:
        await async_engine.dispose()
        await lag_probe.stop()


async def run_async():
    await main()


def run():
    asyncio.run(run_async())


if __name__ == "__main__":
    run()
