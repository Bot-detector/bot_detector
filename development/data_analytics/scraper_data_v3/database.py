import polars as pl
import ptime
import queries
from settings import Settings
from sqlalchemy import create_engine, text

engine = create_engine(url=Settings().database_uri, pool_pre_ping=True)


def read_sql(query: str, params: dict) -> pl.DataFrame:
    with engine.connect() as connection:
        connection.execute(text("SET SESSION wait_timeout = 10;"))
        return pl.read_database(
            connection=connection,
            query=query,
            execute_options={"parameters": params},
        )


@ptime._timer
def get_scrape_batch(last_id: int, batch_size: int) -> pl.DataFrame:
    return read_sql(
        query=queries.SCRAPE_BATCH_SQL,
        params={
            "last_id": last_id,
            "batch_size": batch_size,
        },
    )


@ptime._timer
def get_skill_data(min_id: int, max_id: int) -> pl.DataFrame:
    return read_sql(
        query=queries.SKILL_RANGE_SQL,
        params={
            "min_id": min_id,
            "max_id": max_id,
        },
    )


@ptime._timer
def get_activity_data(min_id: int, max_id: int) -> pl.DataFrame:
    return read_sql(
        query=queries.ACTIVITY_RANGE_SQL,
        params={
            "min_id": min_id,
            "max_id": max_id,
        },
    )


@ptime._timer
def get_full_data(min_id: int, max_id: int) -> pl.DataFrame:
    return read_sql(
        query=queries.FULL_RANGE_SQL,
        params={
            "min_id": min_id,
            "max_id": max_id,
        },
    )
