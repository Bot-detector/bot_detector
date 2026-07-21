import asyncio
import logging

import sqlalchemy as sqla
from bot_detector.database import Settings as DBSettings
from bot_detector.database import get_session_factory
from bot_detector.event_queue.adapters.kafka import (
    KafkaConfig,
    KafkaProducerConfig,
    KafkaSettings,
)
from bot_detector.event_queue.core import QueueProducer
from bot_detector.event_queue.factory import QueueFactory, create_lag_probe
from bot_detector.event_queue.lag_probe import LagProbeProtocol
from bot_detector.event_queue.structs import PlayerBannedStruct
from bot_detector.structs._metadata import MetaData
from pydantic_settings import BaseSettings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    BATCH_SIZE: int = 10_000
    MAX_LAG: int = 100_000
    LAG_SLEEP_SECONDS: int = 10


def _select_banned_players() -> sqla.TextClause:
    """Page through Players flagged as Jagex-banned (label_jagex = 2)."""
    return sqla.text(
        """
        SELECT id, name FROM Players
        WHERE label_jagex = 2 AND id > :player_id
        ORDER BY id ASC
        LIMIT :limit
        """
    )


async def backfill(
    producer: QueueProducer[PlayerBannedStruct],
    session_factory: async_sessionmaker[AsyncSession],
    lag_probe: LagProbeProtocol,
    lag_topic: str,
    lag_group_id: str,
    batch_size: int = 10_000,
    max_lag: int = 100_000,
    lag_sleep_seconds: int = 10,
) -> int:
    """Publish PlayerBanned events for every Jagex-banned player.

    Paginates Players where label_jagex = 2 in pages of `batch_size` and
    publishes one PlayerBannedStruct per player to the players.banned topic.
    Each page is sent in a single producer.put() call. The ban_migration_worker
    consumes these events and writes report_archive rows, so this backfill owns
    no DB writes itself - it is purely a producer. Idempotent at the consumer
    thanks to INSERT IGNORE: a re-run after partial completion only re-emits
    the last page's worth of events before the in-memory cursor was lost.

    Before each page, checks consumer lag on the players.banned topic for the
    ban_migration_worker group. If lag >= max_lag the run sleeps and retries,
    so the backfill cannot outrun the live worker and pile events onto the
    topic while it is catching up.

    Args:
        producer: QueueProducer for PlayerBannedStruct on players.banned.
        session_factory: SQLAlchemy async session factory (read-only pagination).
        lag_probe: Kafka lag probe used to throttle against the live worker.
        lag_topic: Topic whose lag gates the run (players.banned).
        lag_group_id: Consumer group whose lag gates the run.
        batch_size: Rows fetched per page and events per producer.put() call.
        max_lag: Lag threshold above which the run throttles.
        lag_sleep_seconds: Sleep duration when throttled.

    Returns:
        Number of ban events published.

    Raises:
        Exception: If producer.put() returns an error. The run is aborted so
            the failure is surfaced; re-running is safe because the worker's
            INSERT IGNORE makes re-delivered events idempotent.
    """
    sql = _select_banned_players()
    player_id = 0
    published = 0

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
            rows = result.all()

        if not rows:
            logger.info("backfill: no more banned players, exiting")
            break

        events = [
            PlayerBannedStruct(
                metadata=MetaData(version=1, source="job_backfill_banned"),
                player_id=pid,
                name=name,
            )
            for pid, name in rows
        ]

        err = await producer.put(events)
        if err:
            logger.error(
                f"backfill: producer error for player_id={events[0].player_id}: {err}"
            )
            raise err

        published += len(events)
        player_id = events[-1].player_id
        logger.info(
            f"backfill: published up to player_id={player_id} "
            f"({published} total)"
        )

    logger.info(f"backfill: finished, {published} ban events published")
    return published


async def main():
    session_factory, async_engine = get_session_factory(SETTINGS=DBSettings())
    settings = Settings()

    bootstrap_servers = KafkaSettings().bootstrap_servers
    lag_topic = "players.banned"
    lag_group_id = "ban_migration_worker"

    lag_probe = create_lag_probe(
        backend_type="kafka",
        bootstrap_servers=bootstrap_servers,
    )
    if isinstance(lag_probe, Exception):
        raise lag_probe

    producer = QueueFactory.create_queue(
        model=PlayerBannedStruct,
        queue_type="producer",
        backend_type="kafka",
        config=KafkaConfig(
            topic=lag_topic,
            bootstrap_servers=bootstrap_servers,
            producer=True,
            producer_config=KafkaProducerConfig(
                partition_key_fn=lambda message: str(message.player_id % 10),
            ),
        ),
    )
    if isinstance(producer, Exception):
        raise producer
    assert isinstance(producer, QueueProducer)

    await lag_probe.start()
    await producer.start()
    try:
        await backfill(
            producer=producer,
            session_factory=session_factory,
            lag_probe=lag_probe,
            lag_topic=lag_topic,
            lag_group_id=lag_group_id,
            batch_size=settings.BATCH_SIZE,
            max_lag=settings.MAX_LAG,
            lag_sleep_seconds=settings.LAG_SLEEP_SECONDS,
        )
    finally:
        await producer.stop()
        await lag_probe.stop()
        await async_engine.dispose()


async def run_async():
    await main()


def run():
    asyncio.run(run_async())


if __name__ == "__main__":
    run()
