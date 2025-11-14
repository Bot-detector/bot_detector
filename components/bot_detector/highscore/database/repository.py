import json
import logging

import sqlalchemy as sqla
import sqlalchemy.dialects.mysql as sqla_mysql
from bot_detector.highscore.structs import HighscoreBaseStruct
from sqlalchemy import TextClause, func
from sqlalchemy.ext.asyncio import AsyncSession

from .interface import (
    HighscoreDataDailyInterface,
    HighscoreDataLatestInterface,
    HighscoreDataMonthlyInterface,
    HighscoreDataWeeklyInterface,
)
from .structs import (
    HighscoreDataDailyTableStruct,
    HighscoreDataLatestTableStruct,
    HighscoreDataMonthlyTableStruct,
    HighscoreDataWeeklyTableStruct,
)

logger = logging.getLogger(__name__)


class HighscoreDataRepo(HighscoreDataLatestInterface):
    def _create_temp_highscore(self) -> TextClause:
        """Create a temporary highscore table for the latest data."""
        return sqla.text(
            """
            CREATE TEMPORARY TABLE temp_highscore_data (
                player_id BIGINT NOT NULL,
                scrape_date DATE NOT NULL,
                skills JSON NOT NULL,
                activities JSON NOT NULL
            ) ENGINE=InnoDB;
            """
        )

    def _insert_temp_highscore(self) -> TextClause:
        """Insert data into the temporary highscore table."""
        return sqla.text(
            """
            INSERT INTO temp_highscore_data (player_id, scrape_date, skills, activities)
            VALUES (:player_id, :scrape_date, :skills, :activities);
            """
        )

    def _insert_highscore_data_latest(self) -> TextClause:
        return sqla.text(
            """
            INSERT INTO highscore_data_latest (player_id, scrape_date, skills, activities)
            SELECT * FROM (
                SELECT 
                    t.player_id, t.scrape_date, t.skills, t.activities
                FROM temp_highscore_data t
            ) AS new
            ON DUPLICATE KEY UPDATE
                scrape_date = new.scrape_date,
                skills = new.skills,
                activities = new.activities;
            """
        )

    def _insert_highscore_data_daily(self) -> TextClause:
        # TODO: add if statement o nthe on duplicate key update
        # TODO: figure out if we can avoid the update all together

        return sqla.text(
            """
            INSERT INTO highscore_data_daily (player_id, scrape_date, time_to_live, skills, activities)
            SELECT * FROM (
                SELECT 
                    t.player_id, 
                    t.scrape_date, 
                    DATE_ADD(t.scrape_date, INTERVAL 30 DAY) AS time_to_live, 
                    t.skills, 
                    t.activities
                FROM temp_highscore_data t
            ) AS new
            ON DUPLICATE KEY UPDATE
                scrape_date = IF(new.scrape_date > highscore_data_daily.scrape_date, new.scrape_date, highscore_data_daily.scrape_date),
                time_to_live = IF(new.scrape_date > highscore_data_daily.scrape_date, new.time_to_live, highscore_data_daily.time_to_live),
                skills = IF(new.scrape_date > highscore_data_daily.scrape_date, new.skills, highscore_data_daily.skills),
                activities = IF(new.scrape_date > highscore_data_daily.scrape_date, new.activities, highscore_data_daily.activities);
            """
        )

    def _insert_highscore_data_weekly(self) -> TextClause:
        return sqla.text(
            """
            INSERT INTO highscore_data_weekly (player_id, scrape_date, time_to_live, skills, activities)
            SELECT * FROM (
                SELECT 
                    t.player_id, 
                    t.scrape_date, 
                    DATE_ADD(t.scrape_date, INTERVAL 210 DAY) AS time_to_live, 
                    t.skills, 
                    t.activities
                FROM temp_highscore_data t
            ) AS new
            ON DUPLICATE KEY UPDATE
                scrape_date = IF(new.scrape_date > highscore_data_weekly.scrape_date, new.scrape_date, highscore_data_weekly.scrape_date),
                time_to_live = IF(new.scrape_date > highscore_data_weekly.scrape_date, new.time_to_live, highscore_data_weekly.time_to_live),
                skills = IF(new.scrape_date > highscore_data_weekly.scrape_date, new.skills, highscore_data_weekly.skills),
                activities = IF(new.scrape_date > highscore_data_weekly.scrape_date, new.activities, highscore_data_weekly.activities);
            """
        )

    def _insert_highscore_data_monthly(self) -> TextClause:
        return sqla.text(
            """
            INSERT INTO highscore_data_monthly (player_id, scrape_date, time_to_live, skills, activities)
            SELECT * FROM (
                SELECT 
                    t.player_id, 
                    t.scrape_date, 
                    DATE_ADD(t.scrape_date, INTERVAL 900 DAY) AS time_to_live, 
                    t.skills, 
                    t.activities
                FROM temp_highscore_data t
            ) AS new
            ON DUPLICATE KEY UPDATE
                scrape_date = IF(new.scrape_date > highscore_data_monthly.scrape_date, new.scrape_date, highscore_data_monthly.scrape_date),
                time_to_live = IF(new.scrape_date > highscore_data_monthly.scrape_date, new.time_to_live, highscore_data_monthly.time_to_live),
                skills = IF(new.scrape_date > highscore_data_monthly.scrape_date, new.skills, highscore_data_monthly.skills),
                activities = IF(new.scrape_date > highscore_data_monthly.scrape_date, new.activities, highscore_data_monthly.activities);
            """
        )

    async def insert_highscore(
        self,
        async_session: AsyncSession,
        highscore_data: HighscoreBaseStruct,
    ):
        raise NotImplementedError("Use insert_highscore_many for batch inserts.")

    async def insert_highscore_many(
        self,
        async_session: AsyncSession,
        highscore_data: list[HighscoreBaseStruct],
    ):
        """Insert multiple highscore records into the database."""
        if not highscore_data:
            return

        # Drop the temporary table
        await async_session.execute(
            sqla.text("DROP TEMPORARY TABLE IF EXISTS temp_highscore_data;")
        )

        # Create temporary table
        await async_session.execute(self._create_temp_highscore())

        data_list = []
        for data in highscore_data:
            _data = {
                "player_id": data.player_id,
                "scrape_date": data.scrape_date.isoformat(),
                "skills": json.dumps(data.skills),
                "activities": json.dumps(data.activities),
            }
            data_list.append(_data)

        # Insert data into temporary table
        await async_session.execute(self._insert_temp_highscore(), data_list)

        # Insert into latest highscore table
        await async_session.execute(self._insert_highscore_data_latest())

        # Insert into daily highscore table
        await async_session.execute(self._insert_highscore_data_daily())

        # Insert into weekly highscore table
        await async_session.execute(self._insert_highscore_data_weekly())

        # Insert into monthly highscore table
        await async_session.execute(self._insert_highscore_data_monthly())

        # Drop the temporary table
        await async_session.execute(
            sqla.text("DROP TEMPORARY TABLE IF EXISTS temp_highscore_data;")
        )


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
