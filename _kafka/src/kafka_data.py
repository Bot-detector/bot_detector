import random
from datetime import datetime, timedelta
from typing import Generator

from pydantic import BaseModel


class Player(BaseModel):
    id: int
    name: str
    created_at: datetime
    updated_at: datetime | None
    possible_ban: int
    confirmed_ban: int
    confirmed_player: int
    label_id: int
    label_jagex: int


class ScraperHiscoreData(BaseModel):
    skills: dict[str, int]
    activities: dict[str, int]


class MetaData(BaseModel):
    version: int
    source: str


class ScraperData(BaseModel):
    metadata: MetaData
    player_data: Player
    hiscore_data: ScraperHiscoreData | None


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

SKILLS = ["Attack", "Defence", "Strength"]
ACTIVITIES = ["Wintertodt", "Zalcano", "Zulrah"]

MAX_SKILL_XP = 13_000_000
MAX_ACTIVITY_COUNT = 65_000


def create_player() -> Generator[Player, None, None]:
    """Generates Player objects with random creation timestamps."""
    for idx, name in enumerate(NAMES, start=1):
        yield Player(
            id=idx,
            name=name,
            created_at=datetime.fromtimestamp(
                random.randint(1609459200, 1672444800)
            ),  # Random date between 2021-01-01 and 2022-12-31
            updated_at=None,
            possible_ban=0,
            confirmed_ban=0,
            confirmed_player=0,
            label_id=0,
            label_jagex=0,
        )


def create_scraped_data(
    player: Player, n_records: int
) -> Generator[ScraperData, None, None]:
    """
    Generates scraped hiscore data for a given player.
    Produces `n_records` with random updates to skills and activities.
    """
    # Generate or update skills and activities
    skills = {skill: random.randint(2_000_000, MAX_SKILL_XP) for skill in SKILLS}
    activities = {
        activity: random.randint(10, MAX_ACTIVITY_COUNT) for activity in ACTIVITIES
    }
    for record_idx in range(n_records):
        # Update player's `updated_at` field
        player.updated_at = (player.updated_at or player.created_at) + timedelta(days=1)

        # Yield the ScraperData object
        yield ScraperData(
            metadata=MetaData(version=0, source="init"),
            player_data=player,
            hiscore_data=ScraperHiscoreData(
                skills=skills,
                activities=activities,
            ),
        )

        # Randomly modify the skills and activities for subsequent records
        skills = {
            skill: min(value + random.randint(0, 100_000), MAX_SKILL_XP)
            if random.random() > 0.5
            else value
            for skill, value in skills.items()
        }
        activities = {
            activity: min(value + random.randint(0, 100), MAX_ACTIVITY_COUNT)
            if random.random() > 0.5
            else value
            for activity, value in activities.items()
        }


# Example Usage
if __name__ == "__main__":
    random.seed(43)
    # Create players
    player_gen = create_player()

    # Generate scraped data for each player
    for player in player_gen:
        print(f"Player: {player.name}")
        scrape_gen = create_scraped_data(player, n_records=3)
        for scrape_data in scrape_gen:
            print(scrape_data.model_dump(mode="json"))
        print("-" * 40)
