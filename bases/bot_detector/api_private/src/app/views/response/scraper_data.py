from datetime import date, datetime

from pydantic import BaseModel


class SkillView(BaseModel):
    skill_name: str
    skill_value: int


class ActivityView(BaseModel):
    activity_name: str
    activity_value: int


class ScraperDataView(BaseModel):
    created_at: datetime
    record_date: date
    scraper_id: int
    player_id: int
    player_name: str
    skills: list[SkillView]
    activities: list[ActivityView]
