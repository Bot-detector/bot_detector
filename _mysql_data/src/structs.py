from datetime import datetime

from pydantic import BaseModel


class Player(BaseModel):
    id: int
    name: str
    created_at: datetime
    updated_at: datetime | None
    possible_ban: int
    confirmed_ban: int
    confirmed_player: int
    label_id: int
    label_jagex: int
