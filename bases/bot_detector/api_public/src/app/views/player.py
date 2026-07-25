from datetime import datetime

from pydantic import BaseModel, field_validator


class PlayerCreate(BaseModel):
    name: str
    possible_ban: bool | None = 0
    confirmed_ban: bool | None = 0
    confirmed_player: bool | None = 0
    label_id: int | None = 0
    label_jagex: int | None = 0
    ironman: int | None = None
    hardcore_ironman: int | None = None
    ultimate_ironman: int | None = None
    normalized_name: str | None = None


class PlayerUpdate(BaseModel):
    name: str | None = None
    possible_ban: bool | None = None
    confirmed_ban: bool | None = None
    confirmed_player: bool | None = None
    label_id: int | None = None
    label_jagex: int | None = None
    ironman: int | None = None
    hardcore_ironman: int | None = None
    ultimate_ironman: int | None = None
    normalized_name: str | None = None


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
