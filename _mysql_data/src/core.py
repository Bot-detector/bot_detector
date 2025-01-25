import asyncio
import random
import time
from datetime import datetime
from typing import Generator

import sqlalchemy
from database.database import Session
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


def create_player() -> Generator[Player, None, None]:
    """Generates Player objects with random creation timestamps."""
    for idx, name in enumerate(NAMES, start=1):
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
    INSERT INTO Players (id, name, created_at)
    VALUES (:id, :name, :created_at)
    """)
    print(player.name)
    async with Session.begin() as session:
        await session.execute(sql, player.model_dump(mode="json"))


def main():
    time.sleep(10)  # Wait for the database to be ready
    player_gen = create_player()

    async def run():
        await asyncio.gather(
            *[insert_player(p.model_copy(deep=True)) for p in player_gen]
        )

    asyncio.run(run())  # Run the async function in an event loop


if __name__ == "__main__":
    random.seed(43)
    main()
