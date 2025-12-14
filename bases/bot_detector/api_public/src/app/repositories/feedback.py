import logging

from bot_detector.api_public.src.app.views.input.feedback import FeedbackInput
from bot_detector.database.api_public import (
    Player as dbPlayer,
    PredictionFeedback as dbFeedback,
)
from sqlalchemy import and_, insert, select
from sqlalchemy.ext.asyncio import AsyncResult, AsyncSession
from sqlalchemy.sql.expression import Insert, Select

logger = logging.getLogger(__name__)


class Feedback:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def insert_feedback(self, feedback: FeedbackInput) -> tuple[bool, str]:
        sql_select: Select = select(dbPlayer.id)
        sql_select = sql_select.where(dbPlayer.name == feedback.player_name)

        sql_dupe_check: Select = select(dbFeedback)
        sql_dupe_check = sql_dupe_check.where(
            and_(
                dbFeedback.prediction == feedback.prediction,
                dbFeedback.subject_id == feedback.subject_id,
            )
        )

        sql_insert: Insert = insert(dbFeedback)
        data = {
            "voter_id": None,
            "subject_id": feedback.subject_id,
            "prediction": feedback.prediction,
            "confidence": feedback.confidence,
            "vote": feedback.vote,
            "feedback_text": feedback.feedback_text,
            "proposed_label": feedback.proposed_label,
        }

        async with self.session:
            result: AsyncResult = await self.session.execute(sql_select)
            result = result.mappings().first()

            # check if voter exists
            if not result:
                logger.info({"voter_does_not_exist": FeedbackInput})
                await self.session.rollback()
                return False, "voter_does_not_exist"

            voter_id = result["id"]
            sql_dupe_check = sql_dupe_check.where(dbFeedback.voter_id == voter_id)

            result: AsyncResult = await self.session.execute(sql_dupe_check)
            result = result.first()

            # check if duplicate record
            if result:
                logger.info({"duplicate_record": FeedbackInput, "voter id": voter_id})
                await self.session.rollback()
                return False, "duplicate_record"

            # add voter_id and insert
            data["voter_id"] = voter_id
            sql_insert = sql_insert.values(data)
            result: AsyncResult = await self.session.execute(sql_insert)
            await self.session.commit()
        return True, "success"
