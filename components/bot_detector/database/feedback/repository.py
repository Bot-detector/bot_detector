import logging

import sqlalchemy as sqla
from bot_detector.database.player.structs import PlayersTableStruct
from bot_detector.structs import FeedbackExportItem
from sqlalchemy import case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from .structs import PredictionFeedbackTableStruct

logger = logging.getLogger(__name__)


class FeedbackExportRepo:
    async def get_feedback_export(
        self,
        async_session: AsyncSession,
        voter_player_id: int,
    ) -> list[FeedbackExportItem]:
        p_subject = aliased(PlayersTableStruct, name="export_subject")

        is_banned_expr = case(
            (
                sqla.and_(
                    p_subject.possible_ban == True,  # noqa: E712
                    p_subject.label_jagex == 2,
                ),
                True,
            ),
            else_=False,
        )

        sql = sqla.select(
            p_subject.name.label("subject_name"),
            is_banned_expr.label("is_banned"),
            PredictionFeedbackTableStruct.vote,
            PredictionFeedbackTableStruct.prediction,
        ).where(
            PredictionFeedbackTableStruct.voter_id == voter_player_id,
        )

        result = await async_session.execute(sql)
        rows = result.mappings().all()
        return [FeedbackExportItem(**row) for row in rows]
