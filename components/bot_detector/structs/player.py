from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class PlayerStruct(BaseModel):
    id: int
    name: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    possible_ban: bool = False
    confirmed_ban: bool = False
    confirmed_player: bool = False
    label_id: int = 0
    label_jagex: int = 0
    ironman: Optional[bool] = None
    hardcore_ironman: Optional[bool] = None
    ultimate_ironman: Optional[bool] = None
    normalized_name: Optional[str] = None
