import random
from datetime import date, timedelta
from typing import Generator

from pydantic import BaseModel

import osrs_data
from seeders.players_to_scrape import PlayerStruct


class ScraperHiscoreData(BaseModel):
    player_id: int
    scrape_date: date
    time_to_live: date
    skills: dict[str, int] | None
    activities: dict[str, int] | None


class MetaData(BaseModel):
    version: int
    source: str


class ScrapedStruct(BaseModel):
    metadata: MetaData
    player_data: PlayerStruct
    highscore_data: ScraperHiscoreData | None


def create_players_scraped(
    players: list[PlayerStruct], scrapes_per_player: int
) -> Generator[ScrapedStruct, None, None]:
    for player in players:
        skills = {
            skill: random.randint(2_000_000, osrs_data.MAX_SKILL_XP)
            for skill in osrs_data.OSRS_SKILLS
        }
        activities = {
            activity: random.randint(10, osrs_data.MAX_ACTIVITY_COUNT)
            for activity in osrs_data.OSRS_ACTIVITIES
        }

        for _ in range(scrapes_per_player):
            player.updated_at = (player.updated_at or player.created_at) + timedelta(
                days=1
            )

            yield ScrapedStruct(
                metadata=MetaData(version=0, source="init"),
                player_data=player.model_copy(deep=True),
                highscore_data=ScraperHiscoreData(
                    player_id=player.id,
                    scrape_date=player.updated_at.date(),
                    time_to_live=player.updated_at.date() + timedelta(days=30),
                    skills=skills.copy(),
                    activities=activities.copy(),
                ),
            )

            skills = {
                skill: min(value + random.randint(0, 100_000), osrs_data.MAX_SKILL_XP)
                if random.random() > 0.5
                else value
                for skill, value in skills.items()
            }
            activities = {
                activity: min(
                    value + random.randint(0, 100), osrs_data.MAX_ACTIVITY_COUNT
                )
                if random.random() > 0.5
                else value
                for activity, value in activities.items()
            }
