from datetime import datetime

from pydantic import BaseModel


class PlayerStruct(BaseModel):
    id: int
    name: str
    created_at: datetime
    updated_at: datetime | None = None
    possible_ban: bool = False
    confirmed_ban: bool = False
    confirmed_player: bool = False
    label_id: int = 0
    label_jagex: int = 0
    ironman: bool | None = None
    hardcore_ironman: bool | None = None
    ultimate_ironman: bool | None = None
    normalized_name: str | None = None
