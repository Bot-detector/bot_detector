from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncResult, AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql.expression import Select

from src.app.repositories.abstract_repo import AbstractAPI
from src.core.database.models import Activities, PlayerActivities


class PlayerActivityRepo(AbstractAPI):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__()
        self.session = session

    async def insert(self, id):
        raise NotImplementedError

    async def select(
        self,
        scraper_id: int = None,
        activity_id: int = None,
        limit: int = None,
    ):
        table = aliased(PlayerActivities, name="pa")

        sql = Select(Activities.activity_name, table)

        if scraper_id:
            sql = sql.where(table.scraper_id == scraper_id)

        if activity_id:
            sql = sql.where(table.activity_id == activity_id)

        if limit:
            sql = sql.limit(limit)

        sql = sql.join(Activities, table.activity_id == Activities.activity_id)

        async with self.session:
            result: AsyncResult = await self.session.execute(sql)
            result = result.fetchall()
        data = [{"activity_name": name, **jsonable_encoder(hs)} for name, hs in result]
        return data

    async def update(self):
        raise NotImplementedError

    async def delete(self):
        raise NotImplementedError
