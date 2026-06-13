from functools import wraps

import polars as pl
import ptime
import queries
from settings import Settings
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

engine = create_engine(url=Settings().database_uri, pool_pre_ping=True)


MAX_RETRIES = 5


def _retry(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        t = 0
        while True:
            try:
                result = func(*args, **kwargs)
                break
            except OperationalError as e:
                if t >= MAX_RETRIES:
                    raise e
                print(t, e)
                t += 1
        return result

    return wrapper


def read_sql(query: str, params: dict) -> pl.DataFrame:
    with engine.connect() as connection:
        connection.execute(text("SET SESSION wait_timeout = 30;"))
        connection.execute(text("SET time_zone = '+00:00';"))
        return pl.read_database(
            connection=connection,
            query=query,
            execute_options={"parameters": params},
        )


@ptime._timer
@_retry
def get_full_data(start_ts: int, batch_size: int) -> pl.DataFrame:
    return read_sql(
        query=queries.FULL_RANGE_SQL,
        params={
            "start_ts": start_ts,
            "batch_size": batch_size,
        },
    )
