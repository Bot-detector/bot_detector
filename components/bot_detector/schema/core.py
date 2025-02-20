from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class Player(BaseModel):
    id: int
    name: str
    created_at: datetime
    updated_at: datetime | None
    possible_ban: bool
    confirmed_ban: bool
    confirmed_player: bool
    label_id: int
    label_jagex: int


class HighscoreData(BaseModel):
    player_id: int
    scrape_ts: datetime
    scrape_year: Optional[int] = None
    scrape_week: Optional[int] = None
    skills: Optional[dict[str, int]] = None
    activities: Optional[dict[str, int]] = None


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
