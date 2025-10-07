import asyncio
import os
import random
import time
from asyncio import Semaphore
from datetime import datetime
from typing import Generator

import sqlalchemy
from database.database import Session
from sqlalchemy.exc import OperationalError
from structs import Player

# Constants for data generation
NAMES = [
    "extreme4all",
    "ferrariic",
    "championd",
    "snelms deep",
    "420 problems",
    "xedler",
    "kyranm8",
    "thecrinkler",
    "quesorichard",
    "itellyahwat",
    "rs n rambo",
    "stimulism",
    "bateau bbq",
    "tee bowz",
    "n3w y3ar",
    "revs til bow",
    "xapol0x",
    "lauranda",
    "little sex",
    "st4rsd",
    "dalao888",
    "only death93",
    "gravity41",
    "m00kaa",
    "88snakegod88",
    "prainfaya",
    "themission07",
    "im a tempest",
    "laito yagami",
    "the queen 18",
]


async def get_player_count() -> int:
    sql = sqlalchemy.text("""
    SELECT COUNT(*) FROM Players;
    """)
    async with Session.begin() as session:
        result = await session.execute(sql)
        count = result.scalar() or 0
    print(f"Total players: {count}")
    return count


def create_player(names: list[str]) -> Generator[Player, None, None]:
    """Generates Player objects with random creation timestamps."""
    for idx, name in enumerate(names, start=1):
        yield Player(
            id=idx,
            name=name,
            created_at=datetime.fromtimestamp(
                random.randint(1609459200, 1735689600)
            ),  # Random date between 2021-01-01 and 2024-12-31
            updated_at=None,
            possible_ban=0,
            confirmed_ban=0,
            confirmed_player=0,
            label_id=0,
            label_jagex=0,
        )


async def insert_player(player: Player):
    sql = sqlalchemy.text("""
    INSERT IGNORE INTO Players (id, name, created_at)
    VALUES (:id, :name, :created_at)
    """)
    print(player.name)
    async with Session.begin() as session:
        await session.execute(sql, player.model_dump(mode="json"))


async def execute_sql(sql: str, name: str, semaphore: Semaphore):
    print(f"Executing {name}")
    print(sql)
    async with semaphore:
        while True:
            try:
                async with Session.begin() as session:
                    await session.execute(sqlalchemy.text(sql))
                break
            except OperationalError as e:
                sleep = random.random()
                print(f"{sleep=}, {e=}")
                await asyncio.sleep(sleep)
                continue


async def run_sql_file():
    semaphore = Semaphore(10)
    scripts = {}

    for file_name in os.listdir("src/"):
        if not file_name.endswith(".sql"):
            continue

        with open(f"src/{file_name}", "r", encoding="utf-8-sig") as f:
            sql = f.read()
            _sql = sql.split(";")
            if len(_sql) > 1:  # Split the file into individual queries
                for i in range(len(_sql) - 1):
                    if sql[i].strip() == "":
                        continue
                    scripts[f"{file_name}_{i}"] = _sql[i]
        del _sql

    await asyncio.gather(
        *[execute_sql(sql=v, name=k, semaphore=semaphore) for k, v in scripts.items()]
    )


def main():
    time.sleep(15)  # Wait for the database to start

    player_gen = create_player(names=NAMES)

    async def run():
        player_count = await get_player_count()
        if player_count > 100:
            print("Players already exist, skipping insertion.")
            return

        await asyncio.gather(
            *[insert_player(p.model_copy(deep=True)) for p in player_gen]
        )
        await run_sql_file()

    asyncio.run(run())


if __name__ == "__main__":
    random.seed(43)
    main()
