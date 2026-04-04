from datetime import datetime

from pydantic import BaseModel


class DiscordVerificationStruct(BaseModel):
    Entry: int | None = None
    Discord_id: str | None = None
    Player_id: int | None = None
    primary_rsn: bool | None = None
    Code: str | None = None
    verified_status: int | None = None
    token_used: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
