import copy
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import database as db
import polars as pl
import ptime
from osrs import (
    PARQUET_SCHEMA,
    activity_lookup,
    skill_lookup,
)
from settings import Settings

BATCH_SIZE = 50_000
SAVE_THRESHOLD = 100_000
PREFIX = "hsd"
STATE_PATH = f"{Settings().base_path}/{PREFIX}_state.txt"


def read_state(path: str) -> int:
    try:
        with open(path, "r") as f:
            start_ts = f.read().strip()
            return int(start_ts)
    except FileNotFoundError:
        return 0


def save_state(path: str, start_ts: int):
    with open(path, "w+") as f:
        f.write(f"{start_ts}")


@ptime._timer
def save_parquet(df: pl.DataFrame, path: str):
    print(f"\tFinal: {df.shape}, {df.estimated_size()} bytes")
    print(f"\tSaving parquet to {path}")
    df.write_parquet(
        file=path,
        compression="zstd",
        mkdir=True,
    )


@dataclass
class Context:
    df: pl.DataFrame
    start_ts: int


def get_context(start_ts: int) -> Context:
    return Context(df=pl.DataFrame(schema=PARQUET_SCHEMA), start_ts=start_ts)


def detect_columns(df: pl.DataFrame, column: str):
    raw = df.select(
        pl.col(column).map_elements(
            function=lambda x: list(json.loads(x).keys()),
            return_dtype=pl.List(pl.Utf8),
        )
    )
    unique = set(
        raw.explode(column)  # turn list rows into values
        .get_column(column)
        .to_list()
    )
    return {x for x in unique if x is not None}


def save(ctx: Context, _min: int, _max: int) -> Context:
    _t = int(time.time())

    path = f"{Settings().base_path}/{PREFIX}_{_t}_{_min}_{_max}.parquet"
    save_parquet(df=ctx.df, path=path)
    save_state(path=STATE_PATH, start_ts=_max)
    context = get_context(start_ts=_max)
    return context


def int_to_dt(x: int) -> datetime:
    return datetime.fromtimestamp(x, tz=timezone.utc)


def main():
    start_ts = read_state(path=STATE_PATH)
    context = get_context(start_ts=start_ts)

    while True:
        ########################################
        # get batch
        ########################################
        print(f"searching with: {start_ts} == {int_to_dt(start_ts)}")
        df = db.get_full_data(
            start_ts=start_ts,
            batch_size=BATCH_SIZE,
        )
        if df.is_empty():
            print("No more data to process, exiting.")
            break
        min_ts: datetime = df.select(pl.min("scrape_ts")).item()
        max_ts: datetime = df.select(pl.max("scrape_ts")).item()
        print(f"    Received: {min_ts}, {max_ts}")
        print(f"    Received: {min_ts.timestamp()}, {max_ts.timestamp()}")

        if start_ts == max_ts.timestamp():
            raise Exception("start_ts should be equal to min_ts not max_ts")

        _new_start_ts = int(max_ts.timestamp())
        print(f"    Setting start_ts={_new_start_ts} == {int_to_dt(_new_start_ts)}")
        start_ts = copy.copy(_new_start_ts)
        ########################################
        # expand skills and activities from json
        ########################################
        skills = detect_columns(df=df, column="skills")
        activities = detect_columns(df=df, column="activities")

        skills_dtype = pl.Struct({c: pl.UInt32() for c in skills})
        activities_dtype = pl.Struct({c: pl.UInt32() for c in activities})

        df = df.with_columns(
            pl.col("skills").str.json_decode(dtype=skills_dtype),
            pl.col("activities").str.json_decode(dtype=activities_dtype),
        )
        df = df.unnest("skills")
        df = df.unnest("activities")
        ########################################
        # cleanup column names and verify they are all known
        ########################################
        name_map = {}
        for c in df.iter_columns():
            if c.name in ["scrape_ts", "scrape_date", "player_id", "player_name"]:
                continue
            _error = False
            try:
                name_map[c.name] = skill_lookup(c.name)
                continue
            except ValueError:
                _error = True

            try:
                name_map[c.name] = activity_lookup(c.name)
                continue
            except ValueError:
                _error = True

            if _error:
                raise ValueError(f"Unknown column: [{c.name}]")
        df = df.rename(name_map)
        ########################################
        # cast values to UInt32
        ########################################
        df = df.cast(
            {
                k: pl.UInt32
                for k in df.columns
                if k not in ["player_name", "scrape_date", "scrape_ts"]
            }
        )
        df = df.drop(["scrape_ts"])
        ########################################
        # merge to df, if column is not in df, add it with null values first to ensure consistent schema
        ########################################
        context.df = pl.concat([context.df, df], how="diagonal")
        print(f"Batch [{min_ts} - {max_ts}] merged, total rows: {len(context.df)}\n")
        if len(context.df) >= SAVE_THRESHOLD:
            _min = context.start_ts
            _max = int(max_ts.timestamp())
            context = save(ctx=context, _min=_min, _max=_max)

    # final save after loop
    if len(context.df) > 0:
        _min = context.start_ts
        _max = int(max_ts.timestamp())
        context = save(ctx=context, _min=_min, _max=_max)


if __name__ == "__main__":
    main()
