import logging

from bot_detector.api_public.src.core.database.models.feedback import (
    PredictionFeedback as dbFeedback,
)
from bot_detector.api_public.src.core.database.models.player import Player as dbPlayer
from bot_detector.api_public.src.core.database.models.prediction import (
    Prediction as dbPrediction,
)
from bot_detector.api_public.src.core.database.models.report import Report as dbReport
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncResult, AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql.expression import Select

logger = logging.getLogger(__name__)


class Player:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_report_score(self, player_names: tuple[str]):
        voter: dbPlayer = aliased(dbPlayer, name="voter")
        subject: dbPlayer = aliased(dbPlayer, name="subject")

        sub_query: Select = select(
            dbReport.reportedID.distinct().label("reportedID"), dbReport.manual_detect
        )
        sub_query = sub_query.join(voter, dbReport.reportingID == voter.id)
        sub_query = sub_query.where(voter.name.in_(player_names))
        sub_query = sub_query.where(dbReport.manual_detect == 0)

        # Create an alias for the subquery
        sub_query_alias = sub_query.alias("DistinctReports")

        sql: Select = select(
            func.count(func.distinct(subject.id)).label("count"),
            subject.possible_ban,
            subject.confirmed_ban,
            subject.confirmed_player,
            func.coalesce(sub_query_alias.c.manual_detect, 0).label("manual_detect"),
        )
        sql = sql.select_from(sub_query_alias)
        sql = sql.join(
            subject, sub_query_alias.c.reportedID == subject.id
        )  # Use c to access columns
        sql = sql.group_by(
            subject.possible_ban,
            subject.confirmed_ban,
            subject.confirmed_player,
            func.coalesce(sub_query_alias.c.manual_detect, 0).label("manual_detect"),
        )

        async with self.session:
            result: AsyncResult = await self.session.execute(sql)
            await self.session.commit()
        return tuple(result.mappings())

    async def get_feedback_score(self, player_names: list[str]):
        # dbFeedback
        fb_voter: dbPlayer = aliased(dbPlayer, name="feedback_voter")
        fb_subject: dbPlayer = aliased(dbPlayer, name="feedback_subject")

        query: Select = select(
            func.count(func.distinct(fb_subject.id)).label("count"),
            fb_subject.possible_ban,
            fb_subject.confirmed_ban,
            fb_subject.confirmed_player,
        )
        query = query.select_from(dbFeedback)
        query = query.join(fb_voter, dbFeedback.voter_id == fb_voter.id)
        query = query.join(fb_subject, dbFeedback.subject_id == fb_subject.id)
        query = query.where(fb_voter.name.in_(player_names))
        query = query.group_by(
            fb_subject.possible_ban,
            fb_subject.confirmed_ban,
            fb_subject.confirmed_player,
        )

        async with self.session:
            result: AsyncResult = await self.session.execute(query)
            await self.session.commit()
        return tuple(result.mappings())

    async def get_prediction(self, player_names: list[str]):
        query: Select = select(dbPrediction)
        query = query.select_from(dbPrediction)
        query = query.where(dbPrediction.name.in_(player_names))
        async with self.session:
            result: AsyncResult = await self.session.execute(query)
            result = result.scalars().all()
        return jsonable_encoder(result)
