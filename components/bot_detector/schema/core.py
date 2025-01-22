from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class Player(BaseModel):
    id: int
    name: str
    created_at: str
    updated_at: str | None
    possible_ban: int
    confirmed_ban: int
    confirmed_player: int
    label_id: int
    label_jagex: int


class HighscoreData(BaseModel):
    player_id: int
    scrape_ts: datetime
    start_ts: datetime
    scrape_year: int
    scrape_week: int
    skills: Optional[dict[str, int]] = None
    activities: Optional[dict[str, int]] = None
    skills_delta: Optional[dict[str, int]] = None
    activities_delta: Optional[dict[str, int]] = None


class ScraperHiscoreData(BaseModel):
    skills: dict[str, int]
    activities: dict[str, int]


class ScraperData(BaseModel):
    player_data: Player | None
    hiscore_data: ScraperHiscoreData
