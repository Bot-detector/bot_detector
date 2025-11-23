import random
import time
from datetime import date, datetime, timedelta
from typing import Generator, Optional

from pydantic import BaseModel
from pydantic.fields import Field


class MetaData(BaseModel):
    version: int
    source: str


class Equipment(BaseModel):
    equip_head_id: Optional[int] = Field(None, ge=0)
    equip_amulet_id: Optional[int] = Field(None, ge=0)
    equip_torso_id: Optional[int] = Field(None, ge=0)
    equip_legs_id: Optional[int] = Field(None, ge=0)
    equip_boots_id: Optional[int] = Field(None, ge=0)
    equip_cape_id: Optional[int] = Field(None, ge=0)
    equip_hands_id: Optional[int] = Field(None, ge=0)
    equip_weapon_id: Optional[int] = Field(None, ge=0)
    equip_shield_id: Optional[int] = Field(None, ge=0)


class BaseDetection(BaseModel):
    region_id: int = Field(0, ge=0, le=100_000)
    x_coord: int = Field(0, ge=0)
    y_coord: int = Field(0, ge=0)
    z_coord: int = Field(0, ge=0)
    ts: int = Field(int(time.time()), ge=0)
    manual_detect: int = Field(0, ge=0, le=1)
    on_members_world: int = Field(0, ge=0, le=1)
    on_pvp_world: int = Field(0, ge=0, le=1)
    world_number: int = Field(0, ge=300, le=1_000)
    equipment: Equipment
    equip_ge_value: int = Field(0, ge=0)


class Detection(BaseDetection):
    reporter: str = Field(..., min_length=1, max_length=13)
    reported: str = Field(..., min_length=1, max_length=12)


class ParsedDetection(BaseDetection):
    reporter_id: int = Field(..., ge=0)
    reported_id: int = Field(..., ge=0)


class ReportsToInsertStruct(BaseModel):
    metadata: MetaData
    report: ParsedDetection


class PlayerStruct(BaseModel):
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
    player_id: int
    scrape_date: date
    time_to_live: date
    skills: Optional[dict[str, int]] = None
    activities: Optional[dict[str, int]] = None


class ScrapedStruct(BaseModel):
    metadata: MetaData
    player_data: PlayerStruct
    highscore_data: ScraperHiscoreData | None


class ToScrapeStruct(BaseModel):
    metadata: MetaData
    player_data: PlayerStruct


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


def create_player() -> Generator[PlayerStruct, None, None]:
    """Generates Player objects with random creation timestamps."""
    for idx, name in enumerate(NAMES, start=1):
        yield PlayerStruct(
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
    player: PlayerStruct, n_records: int
) -> Generator[ScrapedStruct, None, None]:
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
        yield ScrapedStruct(
            metadata=MetaData(version=0, source="init"),
            player_data=player,
            highscore_data=ScraperHiscoreData(
                player_id=player.id,
                scrape_date=player.updated_at.date(),
                time_to_live=player.updated_at.date() + timedelta(days=30),
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


def create_report() -> Generator[dict, None, None]:
    """Generates report IDs for demonstration purposes."""
    yield {
        "metadata": {"version": 1, "source": "api_public"},
        "report": {
            "region_id": 12598,
            "x_coord": 3167,
            "y_coord": 3490,
            "z_coord": 0,
            "ts": 1763909384,
            "manual_detect": 0,
            "on_members_world": 1,
            "on_pvp_world": 0,
            "world_number": 490,
            "equipment": {
                "equip_head_id": None,
                "equip_amulet_id": None,
                "equip_torso_id": None,
                "equip_legs_id": None,
                "equip_boots_id": None,
                "equip_cape_id": None,
                "equip_hands_id": None,
                "equip_weapon_id": None,
                "equip_shield_id": None,
            },
            "equip_ge_value": 0,
            "reporter_id": 398265,
            "reported_id": 233134407,
        },
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
