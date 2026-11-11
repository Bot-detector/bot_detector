import logging
from typing import cast

import sqlalchemy as sqla
from sqlalchemy import CursorResult, TextClause
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


def _sql_select_banned_bots() -> TextClause:
    return sqla.text(
        """
        SELECT pl.name AS name, pr.prediction AS prediction
        FROM Players pl
        JOIN prediction_latest pr ON pr.player_id = pl.id
        WHERE pl.possible_ban = 1
            AND pl.confirmed_ban = 0
            AND pl.label_jagex = 2
            AND pl.name IS NOT NULL
            AND JSON_EXTRACT(pr.predictions, '$."Real_Player"') < 0.5
        ORDER BY pl.name
        """
    )


def _sql_apply_bot_bans() -> TextClause:
    return sqla.text(
        """
        UPDATE Players pl
        JOIN prediction_latest pr ON pr.player_id = pl.id
        SET pl.confirmed_ban = 1
        WHERE pl.label_jagex = 2
            AND pl.possible_ban = 1
            AND pl.confirmed_ban = 0
            AND pl.name IS NOT NULL
            AND JSON_EXTRACT(pr.predictions, '$."Real_Player"') < 0.5
        """
    )


class BanBroadcastRepo(BanBroadcastInterface):
    """Read-only SELECTs leave the caller's transaction untouched; the
    UPDATE inherits the caller's transaction (base wraps in session.begin()).
    Reads and the UPDATE share one snapshot, but the UPDATE is a current
    read: rows flagged between snapshot and UPDATE are banned yet not in
    the broadcast set."""

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

    async def select_banned_bots(self, async_session: AsyncSession) -> list[BannedBot]:
        result = await async_session.execute(_sql_select_banned_bots())
        rows = result.mappings().all()
        bots = [
            BannedBot(name=row["name"], prediction=row["prediction"]) for row in rows
        ]
        logger.info(f"select_banned_bots: found {len(bots)} predicted bots")
        return bots

    async def apply_bot_bans(self, async_session: AsyncSession) -> int:
        result = await async_session.execute(_sql_apply_bot_bans())
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
