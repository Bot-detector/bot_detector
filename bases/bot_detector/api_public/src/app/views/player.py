from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator


class PlayerCreate(BaseModel):
    name: str
    possible_ban: Optional[bool] = 0
    confirmed_ban: Optional[bool] = 0
    confirmed_player: Optional[bool] = 0
    label_id: Optional[int] = 0
    label_jagex: Optional[int] = 0
    ironman: Optional[int] = None
    hardcore_ironman: Optional[int] = None
    ultimate_ironman: Optional[int] = None
    normalized_name: Optional[str] = None


class PlayerUpdate(BaseModel):
    name: Optional[str] = None
    possible_ban: Optional[bool] = None
    confirmed_ban: Optional[bool] = None
    confirmed_player: Optional[bool] = None
    label_id: Optional[int] = None
    label_jagex: Optional[int] = None
    ironman: Optional[int] = None
    hardcore_ironman: Optional[int] = None
    ultimate_ironman: Optional[int] = None
    normalized_name: Optional[str] = None


class PlayerInDB(PlayerCreate):
    id: int
    created_at: datetime
    updated_at: datetime | None

    @field_validator("created_at", mode="before")
    def parse_created_at(cls, value):
        if isinstance(value, str):
            return datetime.fromisoformat(value)
        if value is None:
            raise ValueError("created_at cannot be None")
        return value


class Player(PlayerInDB):
    pass
