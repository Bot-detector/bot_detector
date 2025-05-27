import logging

import sqlalchemy.dialects.mysql as sqla_mysql
from bot_detector.database.interfaces import (
    HighscoreDataDailyInterface,
    HighscoreDataLatestInterface,
    HighscoreDataMonthlyInterface,
    HighscoreDataWeeklyInterface,
)
from bot_detector.database.structs import (
    HighscoreDataDailyTableStruct,
    HighscoreDataLatestTableStruct,
    HighscoreDataMonthlyTableStruct,
    HighscoreDataWeeklyTableStruct,
)
from bot_detector.structs import HighscoreBaseStruct, HighscoreDataLatestStruct
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class HighscoreDataLatestRepo(HighscoreDataLatestInterface):
    async def insert_highscore(
        self,
        async_session: AsyncSession,
        highscore_data: HighscoreBaseStruct,
    ):
        """Insert a new highscore record into the highscore_data_weekly table."""
        # The latest highscore data table has no time_to_live field,
        _data = highscore_data.model_dump()
        _data.pop("time_to_live", None)

        _table = HighscoreDataLatestTableStruct
        sql = sqla_mysql.insert(_table)
        sql = sql.values([_data])
        sql = sql.on_duplicate_key_update(
            scrape_date=func.if_(
                sql.inserted.scrape_date > _table.scrape_date,
                sql.inserted.scrape_date,
                _table.scrape_date,
            ),
            skills=func.if_(
                sql.inserted.scrape_date > _table.scrape_date,
                sql.inserted.skills,
                _table.skills,
            ),
            activities=func.if_(
                sql.inserted.scrape_date > _table.scrape_date,
                sql.inserted.activities,
                _table.activities,
            ),
        )
        sql = sql.prefix_with("IGNORE")
        await async_session.execute(sql)


class HighscoreDataDailyRepo(HighscoreDataDailyInterface):
    async def insert_highscore(
        self,
        async_session: AsyncSession,
        highscore_data: HighscoreBaseStruct,
    ):
        """Insert a new highscore record into the database."""
        _table = HighscoreDataDailyTableStruct
        sql = sqla_mysql.insert(_table)
        sql = sql.values([highscore_data.model_dump()])
        sql = sql.on_duplicate_key_update(
            scrape_date=func.if_(
                sql.inserted.scrape_date > _table.scrape_date,
                sql.inserted.scrape_date,
                _table.scrape_date,
            ),
            time_to_live=func.if_(
                sql.inserted.scrape_date > _table.scrape_date,
                sql.inserted.time_to_live,
                _table.time_to_live,
            ),
            skills=func.if_(
                sql.inserted.scrape_date > _table.scrape_date,
                sql.inserted.skills,
                _table.skills,
            ),
            activities=func.if_(
                sql.inserted.scrape_date > _table.scrape_date,
                sql.inserted.activities,
                _table.activities,
            ),
        )
        sql = sql.prefix_with("IGNORE")
        await async_session.execute(sql)


class HighscoreDataWeeklyRepo(HighscoreDataWeeklyInterface):
    async def insert_highscore(
        self,
        async_session: AsyncSession,
        highscore_data: HighscoreBaseStruct,
    ):
        """Insert a new highscore record into the highscore_data_weekly table."""
        _table = HighscoreDataWeeklyTableStruct
        sql = sqla_mysql.insert(_table)
        sql = sql.values([highscore_data.model_dump()])
        sql = sql.on_duplicate_key_update(
            scrape_date=func.if_(
                sql.inserted.scrape_date > _table.scrape_date,
                sql.inserted.scrape_date,
                _table.scrape_date,
            ),
            time_to_live=func.if_(
                sql.inserted.scrape_date > _table.scrape_date,
                sql.inserted.time_to_live,
                _table.time_to_live,
            ),
            skills=func.if_(
                sql.inserted.scrape_date > _table.scrape_date,
                sql.inserted.skills,
                _table.skills,
            ),
            activities=func.if_(
                sql.inserted.scrape_date > _table.scrape_date,
                sql.inserted.activities,
                _table.activities,
            ),
        )
        sql = sql.prefix_with("IGNORE")
        await async_session.execute(sql)


class HighscoreDataMonthlyRepo(HighscoreDataMonthlyInterface):
    async def insert_highscore(
        self,
        async_session: AsyncSession,
        highscore_data: HighscoreBaseStruct,
    ):
        """Insert a new highscore record into the highscore_data_weekly table."""
        _table = HighscoreDataMonthlyTableStruct
        sql = sqla_mysql.insert(_table)
        sql = sql.values([highscore_data.model_dump()])
        sql = sql.on_duplicate_key_update(
            scrape_date=func.if_(
                sql.inserted.scrape_date > _table.scrape_date,
                sql.inserted.scrape_date,
                _table.scrape_date,
            ),
            time_to_live=func.if_(
                sql.inserted.scrape_date > _table.scrape_date,
                sql.inserted.time_to_live,
                _table.time_to_live,
            ),
            skills=func.if_(
                sql.inserted.scrape_date > _table.scrape_date,
                sql.inserted.skills,
                _table.skills,
            ),
            activities=func.if_(
                sql.inserted.scrape_date > _table.scrape_date,
                sql.inserted.activities,
                _table.activities,
            ),
        )
        sql = sql.prefix_with("IGNORE")
        await async_session.execute(sql)
