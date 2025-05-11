from datetime import datetime

from pydantic import BaseModel


class PlayerResponse(BaseModel):
    id: int
    name: str
    created_at: datetime
    updated_at: datetime
    possible_ban: bool
    confirmed_ban: bool
    confirmed_player: bool
    label_id: int
    label_jagex: int
    ironman: bool
    hardcore_ironman: bool
    ultimate_ironman: bool
    normalized_name: str
