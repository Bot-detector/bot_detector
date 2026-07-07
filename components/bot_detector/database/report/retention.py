import logging
from datetime import datetime, timedelta
from typing import cast

import sqlalchemy as sqla
from sqlalchemy import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


async def prune_reports(
    session_factory: async_sessionmaker[AsyncSession],
    older_than_days: int = 90,
    batch_size: int = 10_000,
) -> int:
    """Delete report join rows older than the retention window.

    Reporter kill-count / volume is preserved in report_sighting, so pruning
    the report join rows is safe. Deletion runs in fixed-size batches, each in
    its own transaction, until a batch deletes fewer than batch_size rows.

    Args:
        session_factory: SQLAlchemy async session factory.
        older_than_days: Age cutoff in days. Rows with reported_at older than
            now() - older_than_days are deleted.
        batch_size: Maximum number of rows deleted per batch.

    Returns:
        Total number of report rows deleted.
    """
    cutoff = datetime.now() - timedelta(days=older_than_days)
    sql = sqla.text(
        "DELETE FROM report WHERE reported_at < :cutoff LIMIT :batch_size"
    )

    total_deleted = 0
    while True:
        async with session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    sql,
                    params={"cutoff": cutoff, "batch_size": batch_size},
                )
                deleted = cast(CursorResult, result).rowcount

        total_deleted += deleted
        logger.info(f"prune_reports: deleted {deleted} rows (total {total_deleted})")

        if deleted < batch_size:
            break

    logger.info(f"prune_reports: finished, {total_deleted} rows pruned")
    return total_deleted
