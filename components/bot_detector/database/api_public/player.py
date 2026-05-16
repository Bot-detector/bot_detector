import sqlalchemy as sqla
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql.expression import Select

from bot_detector.database.feedback.structs import (
    PredictionFeedbackTableStruct as PredictionFeedback,
)
from bot_detector.database.player.structs import PlayersTableStruct as Player
from bot_detector.database.prediction.structs import (
    PredictionLatestStruct as Prediction_v2,
)


class PlayerRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def sanitize_name(player_name: str) -> str:
        return player_name.lower().replace("_", " ").replace("-", " ").strip()

    async def update_session(self, session: AsyncSession):
        self.session = session

    async def get_report_score(self, player_names: tuple[str, ...]):
        if not isinstance(player_names, tuple):
            raise ValueError("player_names must be a tuple")
        sql_select = """
        select
            count(rs.reporting_id) as count,
            subject.confirmed_ban,
            subject.possible_ban,
            subject.confirmed_player,
            rs.manual_detect
        from report_sighting rs
        join Players voter ON rs.reporting_id = voter.id
        join Players subject ON rs.reported_id = subject.id
        WHERE voter.name in :name 
        GROUP BY
            subject.confirmed_ban,
            subject.possible_ban,
            subject.confirmed_player,
            rs.manual_detect
        """
        params = {"name": player_names}
        data = await self.session.execute(sqla.text(sql_select), params=params)
        result = data.mappings().all()
        return result

    async def get_feedback_score(self, player_names: list[str]):
        fb_voter = aliased(Player, name="feedback_voter")
        fb_subject = aliased(Player, name="feedback_subject")

        query: Select = select(
            func.count(func.distinct(fb_subject.id)).label("count"),
            fb_subject.possible_ban,
            fb_subject.confirmed_ban,
            fb_subject.confirmed_player,
        )
        query = query.select_from(PredictionFeedback)
        query = query.join(fb_voter, PredictionFeedback.voter_id == fb_voter.id)
        query = query.join(fb_subject, PredictionFeedback.subject_id == fb_subject.id)
        query = query.where(fb_voter.name.in_(player_names))
        query = query.group_by(
            fb_subject.possible_ban,
            fb_subject.confirmed_ban,
            fb_subject.confirmed_player,
        )

        result = await self.session.execute(query)
        await self.session.commit()
        return tuple(result.mappings())

    async def get_prediction(self, player_names: list[str]):
        query: Select = select(
            Player.id.label("player_id"),
            Player.name,
            Prediction_v2.created_at,
            Prediction_v2.model_name,
            Prediction_v2.prediction,
            Prediction_v2.confidence,
            Prediction_v2.predictions,
        )
        query = query.select_from(Prediction_v2)
        query = query.join(Player, Prediction_v2.player_id == Player.id)
        query = query.where(Player.name.in_(player_names))

        result = await self.session.execute(query)
        result = result.mappings().all()
        return jsonable_encoder(result)

    async def get(self, player_name: str):
        player_name = self.sanitize_name(player_name)

        sql = sqla.select(Player).where(Player.name == player_name)

        result = await self.session.execute(sql)
        data = result.scalars().all()
        if len(data) == 0:
            return None
        return data[0]

    async def insert(self, player_data: dict):
        player_data["name"] = self.sanitize_name(player_data["name"])
        sql = sqla.insert(Player).values(player_data).prefix_with("IGNORE")
        await self.session.execute(sql)
        await self.session.commit()
        return await self.get(player_name=player_data["name"])

    async def get_or_insert(self, player_name: str):
        player_name = self.sanitize_name(player_name)
        player = await self.get(player_name=player_name)

        if player is None:
            player = await self.insert(player_data={"name": player_name})

        return player
