import logging

import sqlalchemy as sqla
from bot_detector.database.interfaces import HighscoreDataDailyInterface
from bot_detector.database.structs import HighscoreDataDailyTableStruct
from bot_detector.structs import HighscoreDataDailyStruct
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# using mysql
class HighscoreDataDailyRepo(HighscoreDataDailyInterface):
    async def insert_highscore(
        self,
        async_session: AsyncSession,
        highscore_data: HighscoreDataDailyStruct,
    ):
        """Insert a new highscore record into the database."""
        sql = sqla.insert(HighscoreDataDailyTableStruct)
        sql = sql.values([highscore_data.model_dump()])
        sql = sql.prefix_with("IGNORE")
        await async_session.execute(sql)
