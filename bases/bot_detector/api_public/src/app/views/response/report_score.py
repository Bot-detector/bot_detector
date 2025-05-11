from pydantic import BaseModel


class ReportScoreResponse(BaseModel):
    count: int
    possible_ban: bool
    confirmed_ban: bool
    confirmed_player: bool
    manual_detect: bool
