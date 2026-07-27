import time
from dataclasses import dataclass

import database as db
import polars as pl
import ptime
from osrs import PARQUET_SCHEMA, activity_lookup, skill_lookup
from settings import Settings

BATCH_SIZE = 5_000
SAVE_THRESHOLD = 100_000
STATE_PATH = f"{Settings().base_path}/sdv3_state.txt"


def read_state(path: str) -> tuple[int, int]:
    try:
        with open(path, "r") as f:
            line = f.read().strip()
            min_id, max_id = map(int, line.split(","))
            return min_id, max_id
    except FileNotFoundError:
        return 0, 0


def save_state(min_id: int, max_id: int, path: str):
    with open(path, "w+") as f:
        f.write(f"{min_id},{max_id}")


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
    min_id: int
    max_id: int


def get_context(min_id: int, max_id: int) -> Context:
    return Context(df=pl.DataFrame(schema=PARQUET_SCHEMA), min_id=min_id, max_id=max_id)


def main_v2():
    _, max_id = read_state(path=STATE_PATH)
    context = get_context(min_id=max_id, max_id=max_id)

    while True:
        ########################################
        # get batch
        ########################################
        scrape_df = db.get_scrape_batch(
            last_id=context.max_id,
            batch_size=BATCH_SIZE,
        )
        if scrape_df.is_empty():
            break
        ########################################
        # get batch edges
        ########################################
        min_id = scrape_df.select(pl.min("scrape_id")).item()
        max_id = scrape_df.select(pl.max("scrape_id")).item()
        context.max_id = max_id
        ########################################
        # get full data for batch
        ########################################
        full_df = db.get_full_data(min_id=min_id, max_id=max_id)
        print(f"\tFull data: {full_df.shape}")
        ########################################
        # pivot the whole df
        ########################################
        full_df = full_df.pivot(
            on="_name",
            values="_value",
            index=["scrape_id", "scrape_date", "player_id", "player_name"],
            aggregate_function="min",
        )

        ########################################
        # cleanup column names and verify they are all known
        ########################################
        name_map = {}
        for c in full_df.iter_columns():
            if c.name in ["scrape_id", "scrape_date", "player_id", "player_name"]:
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

        full_df = full_df.rename(name_map)
        ########################################
        # cast values to UInt32
        ########################################
        full_df = full_df.cast(
            {
                k: pl.UInt32
                for k in full_df.columns
                if k not in ["player_name", "scrape_date"]
            }
        )
        ########################################
        # merge to df, if column is not in df, add it with null values first to ensure consistent schema
        ########################################
        context.df = pl.concat([context.df, full_df], how="diagonal")
        print(f"Batch [{min_id} - {max_id}] merged, total rows: {len(context.df)}\n")
        if len(context.df) >= SAVE_THRESHOLD:
            _min = context.min_id
            _max = context.max_id
            _t = int(time.time())

            path = f"{Settings().base_path}/sdv3_{_t}_{_min}_{_max}.parquet"
            save_parquet(df=context.df, path=path)
            save_state(min_id=_min, max_id=_max, path=STATE_PATH)
            context = get_context(min_id=_max, max_id=_max)

    # final save after loop
    if len(context.df) > 0:
        _min = context.min_id
        _max = context.max_id
        _t = int(time.time())

        path = f"{Settings().base_path}/sdv3_{_t}_{_min}_{_max}.parquet"
        save_parquet(df=context.df, path=path)
        save_state(min_id=_min, max_id=_max, path=STATE_PATH)


if __name__ == "__main__":
    main_v2()
