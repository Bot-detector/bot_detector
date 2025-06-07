import logging

from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncResult, AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql.expression import Select

from src.app.repositories.abstract_repo import AbstractAPI
from src.core.database.models import (  # playerHiscoreData,; PlayerHiscoreDataXPChange,
    PlayerHiscoreDataLatest,
)
from src.core.database.models.player import Player

logger = logging.getLogger(__name__)


class HighscoreRepo(AbstractAPI):
    def __init__(self, session) -> None:
        super().__init__()
        self.session: AsyncSession = session

    def insert(self):
        raise NotImplementedError

    async def select(
        self, player_id: int, label_id: int, limit: int, many: bool
    ) -> dict:
        table = aliased(PlayerHiscoreDataLatest, name="phd")
        player = aliased(Player, name="pl")

        sql = Select(player.name, table)
        sql = sql.join(target=player, onclause=table.Player_id == player.id)

        if player_id:
            if many:
                sql = sql.where(table.Player_id >= player_id)
            else:
                sql = sql.where(table.Player_id == player_id)

        if label_id:
            sql = sql.where(player.label_id == label_id)

        sql = sql.limit(limit)

        async with self.session:
            result: AsyncResult = await self.session.execute(sql)
            result = result.fetchall()
        data = [{"name": name, **jsonable_encoder(hs)} for name, hs in result]
        return data

    async def update(self):
        raise NotImplementedError

    async def delete(self):
        raise NotImplementedError
