import asyncio
import logging
from typing import Iterable, Optional

import sqlalchemy as sqla
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncResult, AsyncSession
from sqlalchemy.orm import aliased

from bot_detector.database.structs import (
    PlayersTableStruct,
    PredictionsFeedbackTableStruct,
    PredictionsTableStruct,
)
from bot_detector.structs import (
    FeedbackScoreResponse,
    PlayerCreate,
    PlayerInDB,
    PredictionResponse,
    ReportScoreResponse,
)

from ..domain.cache import SimpleALRUCache

logger = logging.getLogger(__name__)


def model_to_dict(model) -> dict:
    """Convert an SQLAlchemy model instance to a dictionary."""
    return {c.name: getattr(model, c.name) for c in model.__table__.columns}


class PlayerService:
    """Encapsulates all player-related business logic including caching."""

    def __init__(
        self,
        session: AsyncSession,
        cache: Optional[SimpleALRUCache] = None,
    ) -> None:
        self.session = session
        self.cache = cache or SimpleALRUCache()

    def sanitize_name(self, player_name: str) -> str:
        return player_name.lower().replace("_", " ").replace("-", " ").strip()

    async def update_session(self, session: AsyncSession) -> None:
        self.session = session

    async def get_report_score(
        self, player_names: tuple[str, ...]
    ) -> list[ReportScoreResponse]:
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
        data = await self.session.execute(
            sqla.text(sql_select), params={"name": player_names}
        )
        result = data.mappings().all()
        return [ReportScoreResponse(**item) for item in result]

    async def get_feedback_score(
        self, player_names: list[str]
    ) -> tuple[FeedbackScoreResponse, ...]:
        fb_voter = aliased(PlayersTableStruct, name="feedback_voter")
        fb_subject = aliased(PlayersTableStruct, name="feedback_subject")

        query: Select = select(
            func.count(func.distinct(fb_subject.id)).label("count"),
            fb_subject.possible_ban,
            fb_subject.confirmed_ban,
            fb_subject.confirmed_player,
        )
        query = query.select_from(PredictionsFeedbackTableStruct)
        query = query.join(
            fb_voter, PredictionsFeedbackTableStruct.voter_id == fb_voter.id
        )
        query = query.join(
            fb_subject, PredictionsFeedbackTableStruct.subject_id == fb_subject.id
        )
        query = query.where(fb_voter.name.in_(player_names))
        query = query.group_by(
            fb_subject.possible_ban,
            fb_subject.confirmed_ban,
            fb_subject.confirmed_player,
        )

        result: AsyncResult = await self.session.execute(query)
        await self.session.commit()
        return tuple(FeedbackScoreResponse(**row) for row in result.mappings())

    async def get_prediction(self, player_names: list[str]) -> list[dict]:
        query: Select = select(PredictionsTableStruct)
        query = query.where(PredictionsTableStruct.name.in_(player_names))
        result: AsyncResult = await self.session.execute(query)
        rows = result.scalars().all()
        return jsonable_encoder([model_to_dict(row) for row in rows])

    async def get(self, player_name: str) -> Optional[PlayerInDB]:
        player_name = self.sanitize_name(player_name)
        sql = select(PlayersTableStruct).where(PlayersTableStruct.name == player_name)
        result = await self.session.execute(sql)
        row = result.scalars().first()
        if row is None:
            return None
        try:
            return PlayerInDB(**model_to_dict(row))
        except ValidationError as exc:
            logger.error("Validation error while loading player: %s", exc)
            return None

    async def get_cache(self, player_name: str) -> Optional[PlayerInDB]:
        player_name = self.sanitize_name(player_name)
        if self.cache is None:
            return await self.get(player_name=player_name)

        cached_player = await self.cache.get(key=player_name)
        if isinstance(cached_player, PlayerInDB):
            if self.cache.hits % 100 == 0 and self.cache.hits > 0:
                logger.info("cache hits=%s misses=%s", self.cache.hits, self.cache.misses)
            return cached_player

        player = await self.get(player_name=player_name)
        if isinstance(player, PlayerInDB):
            await self.cache.put(key=player_name, value=player)
        return player

    async def insert(self, player_name: str) -> Optional[PlayerInDB]:
        payload = PlayerCreate(name=self.sanitize_name(player_name))
        sql = (
            sqla.insert(PlayersTableStruct)
            .values(payload.model_dump())
            .prefix_with("IGNORE")
        )
        await self.session.execute(sql)
        await self.session.commit()
        return await self.get(player_name=payload.name)

    async def get_or_insert(
        self, player_name: str, *, cached: bool = True
    ) -> Optional[PlayerInDB]:
        player_name = self.sanitize_name(player_name)
        player = (
            await self.get_cache(player_name=player_name)
            if cached
            else await self.get(player_name=player_name)
        )
        if player is None:
            player = await self.insert(player_name=player_name)
        return player

    async def ensure_player_ids(
        self, player_names: Iterable[str]
    ) -> dict[str, int]:
        tasks = [self.get_or_insert(player_name=name) for name in player_names]
        players = await asyncio.gather(*tasks)
        return {
            player.name: player.id
            for player in players
            if isinstance(player, PlayerInDB)
        }

    async def enrich_predictions(
        self, player_names: list[str], breakdown: bool
    ) -> list[PredictionResponse]:
        data = await self.get_prediction(player_names=player_names)
        return [PredictionResponse.from_data(d, breakdown) for d in data]
