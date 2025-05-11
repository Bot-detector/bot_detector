import logging

import sqlalchemy as sqla
from bot_detector.api_public.src.app.views.player import PlayerCreate, PlayerInDB
from bot_detector.api_public.src.core._cache import SimpleALRUCache
from bot_detector.api_public.src.core.database.models.feedback import (
    PredictionFeedback as dbFeedback,
)
from bot_detector.api_public.src.core.database.models.player import Player as dbPlayer
from bot_detector.api_public.src.core.database.models.prediction import (
    Prediction as dbPrediction,
)
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncResult, AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql.expression import Select

# from bot_detector.api_public.src.core.database.models.report import Report as dbReport

logger = logging.getLogger(__name__)


def model_to_dict(model):
    """Converts an SQLAlchemy model instance to a dictionary."""
    return {c.name: getattr(model, c.name) for c in model.__table__.columns}


class Player:
    def __init__(
        self,
        session: AsyncSession,
        cache: SimpleALRUCache = SimpleALRUCache(),
    ) -> None:
        self.session = session
        self.cache = cache

    def sanitize_name(self, player_name: str) -> str:
        return player_name.lower().replace("_", " ").replace("-", " ").strip()

    async def update_session(self, session: AsyncSession):
        self.session = session

    async def get_report_score(self, player_names: tuple[str, ...]):
        if not isinstance(player_names, tuple):
            raise Exception()
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

        result: AsyncResult = await self.session.execute(query)
        await self.session.commit()
        return tuple(result.mappings())

    async def get_prediction(self, player_names: list[str]):
        query: Select = select(dbPrediction)
        query = query.select_from(dbPrediction)
        query = query.where(dbPrediction.name.in_(player_names))

        result: AsyncResult = await self.session.execute(query)
        result = result.scalars().all()
        return jsonable_encoder(result)

    async def get(self, player_name: str) -> PlayerInDB:
        assert isinstance(player_name, str)
        player_name = self.sanitize_name(player_name)

        sql = sqla.select(dbPlayer).where(dbPlayer.name == player_name)

        result = await self.session.execute(sql)
        data = result.scalars().all()
        try:
            if len(data) == 0:
                return None
            player_in_db = PlayerInDB(**model_to_dict(data[0]))
        except ValidationError as e:
            logger.error(f"Validation error: {e.json()}")
            return None
        return player_in_db

    async def get_cache(self, player_name: str) -> PlayerInDB:
        player_name = self.sanitize_name(player_name)
        player = await self.cache.get(key=player_name)

        if isinstance(player, PlayerInDB):
            if self.cache.hits % 100 == 0 and self.cache.hits > 0:
                logger.info(f"hits: {self.cache.hits}, misses: {self.cache.misses}")
            return player

        player = await self.get(player_name=player_name)

        if isinstance(player, PlayerInDB):
            await self.cache.put(key=player_name, value=player)
        return player

    async def insert(self, player: PlayerCreate) -> PlayerInDB:
        player.name = self.sanitize_name(player.name)
        sql = sqla.insert(dbPlayer).values(player.model_dump()).prefix_with("IGNORE")
        await self.session.execute(sql)
        await self.session.commit()
        return await self.get(player_name=player.name)

    async def get_or_insert(self, player_name: str, cached=True) -> PlayerInDB:
        player_name = self.sanitize_name(player_name)

        if cached:
            player = await self.get_cache(player_name=player_name)
        else:
            player = await self.get(player_name=player_name)

        if player is None:
            player = await self.insert(PlayerCreate(name=player_name))

        return player
