from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncResult, AsyncSession
from sqlalchemy.sql.expression import Select

from src.core.database.models.player import Player


class PlayerRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def select(
        self,
        player_id: int,
        player_name: str,
        label_id: int,
        greater_than: bool,
        limit: int = 1_000,
    ):
        table = Player
        sql = Select(table)

        if player_name:
            sql = sql.where(table.name == player_name)

        if label_id:
            sql = sql.where(table.label_id == label_id)

        if player_id:
            if greater_than:
                sql = sql.where(table.id >= player_id)
            else:
                sql = sql.where(table.id == player_id)

        sql = sql.order_by(table.id.asc())
        sql = sql.limit(limit)

        async with self.session:
            result: AsyncResult = await self.session.execute(sql)
            result = result.scalars().all()
        return jsonable_encoder(result)
