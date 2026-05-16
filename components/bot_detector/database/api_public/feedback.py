from sqlalchemy import and_, insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.expression import Insert, Select

from bot_detector.database.feedback.structs import (
    PredictionFeedbackTableStruct as PredictionFeedback,
)
from bot_detector.database.player.structs import PlayersTableStruct as Player


class FeedbackRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def insert_feedback(self, feedback_data: dict) -> tuple[bool, str]:
        sql_select: Select = select(Player.id)
        sql_select = sql_select.where(Player.name == feedback_data["player_name"])

        sql_dupe_check: Select = select(PredictionFeedback)
        sql_dupe_check = sql_dupe_check.where(
            and_(
                PredictionFeedback.prediction == feedback_data["prediction"],
                PredictionFeedback.subject_id == feedback_data["subject_id"],
            )
        )

        sql_insert: Insert = insert(PredictionFeedback)
        data = {
            "voter_id": None,
            "subject_id": feedback_data["subject_id"],
            "prediction": feedback_data["prediction"],
            "confidence": feedback_data["confidence"],
            "vote": feedback_data["vote"],
            "feedback_text": feedback_data["feedback_text"],
            "proposed_label": feedback_data["proposed_label"],
        }

        async with self.session:
            result = await self.session.execute(sql_select)
            result = result.mappings().first()

            if not result:
                await self.session.rollback()
                return False, "voter_does_not_exist"

            voter_id = result["id"]
            sql_dupe_check = sql_dupe_check.where(
                PredictionFeedback.voter_id == voter_id
            )

            result = await self.session.execute(sql_dupe_check)
            result = result.first()

            if result:
                await self.session.rollback()
                return False, "duplicate_record"

            data["voter_id"] = voter_id
            sql_insert = sql_insert.values(data)
            await self.session.execute(sql_insert)
            await self.session.commit()
        return True, "success"
