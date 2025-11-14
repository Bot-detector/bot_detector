import asyncio
import logging

import sqlalchemy as sqla
from bot_detector.core.database import Settings as DBSettings, get_session_factory
from pydantic_settings import BaseSettings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    LIMIT: int = 10000


def create_temp_table():
    sql = sqla.text(
        """CREATE TEMPORARY TABLE tmp_player_ids (id BIGINT PRIMARY KEY);"""
    )
    return sql


def insert_temp_table():
    sql = sqla.text(
        """
        INSERT INTO tmp_player_ids
        SELECT id FROM Players 
        WHERE 1=1 
            AND possible_ban = 0 
            AND id > :player_id
        limit :limit
        """
    )
    return sql


def select_temp_table():
    sql = sqla.text(
        """
        select id from tmp_player_ids order by id desc limit 1;
        """
    )
    return sql


def delete_highscore_data_daily():
    sql = sqla.text("""
	DELETE hdd
	FROM highscore_data_daily hdd
	JOIN tmp_player_ids pl ON hdd.player_id = pl.id
	WHERE hdd.time_to_live < CURDATE();
    """)
    return sql


async def prune(async_session: async_sessionmaker[AsyncSession]):
    sql_drop_tmp = sqla.text("DROP TABLE IF EXISTS tmp_player_ids;")
    sql_create_tmp = create_temp_table()
    sql_insert_tmp = insert_temp_table()
    sql_select_tmp = select_temp_table()
    sql_row_count = sqla.text("select ROW_COUNT();")
    sql_delete_hdd = delete_highscore_data_daily()

    player_id = 0
    while True:
        try:
            async with async_session() as session:
                async with session.begin():
                    # Drop and create temp table each loop
                    await session.execute(sql_drop_tmp)
                    await session.execute(sql_create_tmp)
                    params = {"player_id": player_id, "limit": Settings().LIMIT}
                    await session.execute(sql_insert_tmp, params=params)

                    result = await session.scalars(sql_select_tmp)
                    new_player_id = result.first()  # This returns an int or None

                    if new_player_id is None:
                        logger.info("No more players to process, break loop")
                        break

                    player_id = new_player_id
                    logger.info(f"Processed up to player_id: {player_id}")

                    # Perform deletion after temp table is populated
                    await session.execute(sql_delete_hdd)
                    result = await session.scalars(sql_row_count)
                    rows_deleted = result.first()
                    logger.info(f"Deleted {rows_deleted} records")

        except Exception as e:
            logger.error(f"Error during prune loop: {e}")
            break


async def main():
    async_session, async_engine = get_session_factory(SETTINGS=DBSettings())
    await prune(async_session)


async def run_async():
    await main()


def run():
    asyncio.run(run_async())


if __name__ == "__main__":
    run()
