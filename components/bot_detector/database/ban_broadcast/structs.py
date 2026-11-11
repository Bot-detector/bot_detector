from pydantic import BaseModel


class BanCounts(BaseModel):
    """Counts of players flagged by Jagex (label_jagex = 2) not yet applied."""

    total_bans: int
    real_player_bans: int
    no_data_bans: int


class BannedBot(BaseModel):
    """A player predicted as a bot and pending ban application."""

    player_id: int
    name: str
    prediction: str
