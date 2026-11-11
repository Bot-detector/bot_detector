import logging
from typing import cast

import sqlalchemy as sqla
from sqlalchemy import CursorResult, TextClause, bindparam
from sqlalchemy.ext.asyncio import AsyncSession

from .interface import BanBroadcastInterface
from .structs import BanCounts, BannedBot

logger = logging.getLogger(__name__)

# Must mirror the prediction label written by worker_ml (ml_api.Prediction):
# the prediction column stores 'Real_Player', and the JSON blob uses the
# same key. Case matters for the JSON path (JSON_EXTRACT is case-sensitive).
REAL_PLAYER_LABEL = "Real_Player"


def _sql_count_banned_players() -> TextClause:
    return sqla.text(
        """
        SELECT COUNT(*) AS bans
        FROM Players
        WHERE possible_ban = 1
            AND confirmed_ban = 0
            AND label_jagex = 2
        """
    )


def _sql_count_banned_real_players() -> TextClause:
    return sqla.text(
        """
        SELECT COUNT(pl.id) AS real_bans
        FROM Players pl
        JOIN prediction_latest pr ON pr.player_id = pl.id
        WHERE pl.possible_ban = 1
            AND pl.confirmed_ban = 0
            AND pl.label_jagex = 2
            AND pr.prediction = :real_player_label
        """
    )


def _sql_count_banned_no_data() -> TextClause:
    return sqla.text(
        """
        SELECT COUNT(pl.id) AS no_data_bans
        FROM Players pl
        WHERE pl.possible_ban = 1
            AND pl.confirmed_ban = 0
            AND pl.label_jagex = 2
            AND NOT EXISTS (
                SELECT 1 FROM highscore_data_latest h
                WHERE h.player_id = pl.id
            )
        """
    )


def _sql_select_banned_bots_page() -> TextClause:
    """One page of pending bots, keyed by id cursor (backfill idiom)."""
    return sqla.text(
        """
        SELECT pl.id AS player_id, pl.name AS name, pr.prediction AS prediction
        FROM Players pl
        JOIN prediction_latest pr ON pr.player_id = pl.id
        WHERE pl.possible_ban = 1
            AND pl.confirmed_ban = 0
            AND pl.label_jagex = 2
            AND pl.name IS NOT NULL
            AND pl.id > :player_id
            AND JSON_EXTRACT(pr.predictions, '$."Real_Player"') < 0.5
        ORDER BY pl.id
        LIMIT :limit
        """
    )


def _sql_apply_bot_bans() -> TextClause:
    """Single-table PK update for one batch of vetted ids.

    No JOIN and no JSON predicate: the ids were vetted by
    _sql_select_banned_bots_page, so the update locks only Players rows,
    confirmed_ban = 0 keeps rowcount equal to rows changed this batch,
    and re-applying an already-committed batch is a no-op.
    """
    return (
        sqla.text(
            """
            UPDATE Players
            SET confirmed_ban = 1
            WHERE id IN :ids
                AND confirmed_ban = 0
            """
        )
        .bindparams(bindparam("ids", expanding=True))
        .execution_options(synchronize_session=False)
    )


class BanBroadcastRepo(BanBroadcastInterface):
    """Reads paginate by id cursor inside the caller's transaction; the
    caller re-invokes apply_bot_bans per id batch, each in its own short
    transaction - so row locks are held for milliseconds on PK lookups
    instead of one long JOIN update. The applied set is the announced set
    by construction (ids came from the pages just read)."""

    async def get_ban_counts(self, async_session: AsyncSession) -> BanCounts:
        total_bans = await self._count(async_session, _sql_count_banned_players())
        real_player_bans = await self._count(
            async_session,
            _sql_count_banned_real_players(),
            params={"real_player_label": REAL_PLAYER_LABEL},
        )
        no_data_bans = await self._count(async_session, _sql_count_banned_no_data())
        return BanCounts(
            total_bans=total_bans,
            real_player_bans=real_player_bans,
            no_data_bans=no_data_bans,
        )

    async def select_banned_bots(
        self, async_session: AsyncSession, batch_size: int
    ) -> list[BannedBot]:
        bots: list[BannedBot] = []
        player_id = 0
        while True:
            result = await async_session.execute(
                _sql_select_banned_bots_page(),
                params={"player_id": player_id, "limit": batch_size},
            )
            rows = result.mappings().all()
            if not rows:
                break
            bots.extend(
                BannedBot(
                    player_id=row["player_id"],
                    name=row["name"],
                    prediction=row["prediction"],
                )
                for row in rows
            )
            player_id = rows[-1]["player_id"]
        logger.info(f"select_banned_bots: found {len(bots)} predicted bots")
        return bots

    async def apply_bot_bans(
        self, async_session: AsyncSession, player_ids: list[int]
    ) -> int:
        result = await async_session.execute(
            _sql_apply_bot_bans(), params={"ids": player_ids}
        )
        updated = cast(CursorResult, result).rowcount
        logger.info(f"apply_bot_bans: confirmed_ban set on {updated} players")
        return updated

    async def _count(
        self,
        async_session: AsyncSession,
        sql: TextClause,
        params: dict | None = None,
    ) -> int:
        value = await async_session.scalar(sql, params)
        # COUNT(*) always yields one row; guard anyway so a driver quirk
        # fails here instead of as a confusing pydantic ValidationError.
        return int(value or 0)
