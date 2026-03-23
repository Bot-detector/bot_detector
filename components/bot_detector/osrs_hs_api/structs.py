from pydantic import BaseModel


class Skill(BaseModel):
    id: int
    name: str
    rank: int
    level: int
    xp: int


class Activity(BaseModel):
    id: int
    name: str
    rank: int
    score: int


class PlayerStats(BaseModel):
    skills: list[Skill]
    activities: list[Activity]