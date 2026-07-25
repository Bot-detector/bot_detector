
from pydantic import BaseModel, Field


class FeedbackScore(BaseModel):
    count: int
    possible_ban: bool
    confirmed_ban: bool
    confirmed_player: bool
    vote: int | None = Field(None, ge=-1, le=1)
