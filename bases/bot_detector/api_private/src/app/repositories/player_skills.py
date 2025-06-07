from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncResult, AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql.expression import Select

from src.app.repositories.abstract_repo import AbstractAPI
from src.core.database.models import PlayerSkills, Skills


class PlayerSkillsRepo(AbstractAPI):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__()
        self.session = session

    async def insert(self, id):
        raise NotImplementedError

    async def select(
        self,
        scraper_id: int = None,
        skill_id: int = None,
        limit: int = None,
    ):
        table = aliased(PlayerSkills, name="ps")

        sql = Select(Skills.skill_name, table)

        if scraper_id:
            sql = sql.where(table.scraper_id == scraper_id)

        if skill_id:
            sql = sql.where(table.skill_id == skill_id)

        if limit:
            sql = sql.limit(limit)

        sql = sql.join(Skills, table.skill_id == Skills.skill_id)

        async with self.session:
            result: AsyncResult = await self.session.execute(sql)
            result = result.fetchall()
        data = [{"skill_name": name, **jsonable_encoder(hs)} for name, hs in result]
        return data

    async def update(self):
        raise NotImplementedError

    async def delete(self):
        raise NotImplementedError
