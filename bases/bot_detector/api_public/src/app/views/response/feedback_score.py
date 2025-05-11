from pydantic import BaseModel


class FeedbackScoreResponse(BaseModel):
    count: int
    possible_ban: bool
    confirmed_ban: bool
    confirmed_player: bool
