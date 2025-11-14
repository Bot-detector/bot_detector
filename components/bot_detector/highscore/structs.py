from datetime import date
from typing import Optional

from pydantic import BaseModel


class HighscoreBaseStruct(BaseModel):
    player_id: int
    scrape_date: date
    time_to_live: date
    skills: Optional[dict[str, int]] = None
    activities: Optional[dict[str, int]] = None


class HighscoreDataBaseStruct(HighscoreBaseStruct):
    scrape_year: int
    scrape_month: int
    scrape_week: int


class HighscoreDataLatestStruct(HighscoreDataBaseStruct):
    pass


class HighscoreDataDailyStruct(HighscoreDataBaseStruct):
    pass


class HighscoreDataWeeklyStruct(HighscoreDataBaseStruct):
    pass


class HighscoreDataMonthlyStruct(HighscoreDataBaseStruct):
    pass


__all__ = [
    "HighscoreBaseStruct",
    "HighscoreDataBaseStruct",
    "HighscoreDataDailyStruct",
    "HighscoreDataWeeklyStruct",
    "HighscoreDataMonthlyStruct",
    "HighscoreDataLatestStruct",
]
