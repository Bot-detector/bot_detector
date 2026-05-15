import logging

import sqlalchemy as sqla
from bot_detector.database.player.structs import PlayersTableStruct
from bot_detector.structs import FeedbackExportItem
from sqlalchemy import case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from bot_detector.database.feedback.structs import PredictionFeedbackTableStruct

logger = logging.getLogger(__name__)


class FeedbackExportRepo:
    async def get_feedback_export(
        self,
        async_session: AsyncSession,
        voter_player_id: int | None = None,
        voter_player_name: str | None = None,
    ) -> list[FeedbackExportItem]:
        if voter_player_id is None and voter_player_name is None:
            raise ValueError(
                "Either voter_player_id or voter_player_name must be provided"
            )

        feedback = aliased(PredictionFeedbackTableStruct, name="feedback")
        voter = aliased(PlayersTableStruct, name="voter")
        subject = aliased(PlayersTableStruct, name="subject")

        is_banned_expr = case(
            (
                sqla.and_(
                    subject.possible_ban == 1,
                    subject.label_jagex == 2,
                ),
                True,
            ),
            else_=False,
        )

        sql = (
            sqla.select(
                subject.name.label("subject_name"),
                is_banned_expr.label("is_banned"),
                feedback.vote,
                feedback.prediction,
            )
            .join(
                feedback,
                feedback.subject_id == subject.id,
            )
            .join(
                voter,
                feedback.voter_id == voter.id,
            )
        )

        if voter_player_id is not None:
            sql = sql.where(voter.id == voter_player_id)
        if voter_player_name is not None:
            sql = sql.where(voter.name == voter_player_name)

        result = await async_session.execute(sql)
        rows = result.mappings().all()
        return [FeedbackExportItem.model_validate(row) for row in rows]
