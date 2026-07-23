import logging

from bot_detector.database.report import migrate_banned_player_reports
from bot_detector.event_queue.structs import PlayerBannedStruct
from bot_detector.worker.core import Worker
from bot_detector.worker_ban_migration.adapter import transform_player_banned
from bot_detector.worker_ban_migration.metrics import (
    accounts_migrated_counter,
    rows_migrated_counter,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


class BanMigrationWorker(Worker[PlayerBannedStruct]):
    def __init__(
        self,
        worker_id: int,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._id = worker_id
        self._session_factory = session_factory

    async def handle(self, batch: list[PlayerBannedStruct]) -> list[PlayerBannedStruct]:
        """Process each ban event independently.

        Per-record failures are isolated: the offending record is returned for
        requeue while the rest of the batch is progressed. Records with an
        unsupported metadata version are skipped (not requeued).
        """
        logger.info(f"[{self._id}] consumed {len(batch)} ban events")
        failed: list[PlayerBannedStruct] = []
        for record in batch:
            reported_id = transform_player_banned(record)
            if reported_id is None:
                logger.info(f"[{self._id}] skipping invalid ban event")
                continue
            try:
                inserted = await migrate_banned_player_reports(
                    session_factory=self._session_factory,
                    reported_id=reported_id,
                )
            except Exception as e:
                logger.error(
                    f"[{self._id}] failed to migrate reported_id={reported_id}: {e}",
                    exc_info=True,
                )
                failed.append(record)
                continue
            accounts_migrated_counter.inc()
            rows_migrated_counter.inc(inserted)
            logger.info(
                f"[{self._id}] archived {inserted} rows for reported_id={reported_id}"
            )
        return failed
