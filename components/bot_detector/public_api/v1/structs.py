from pydantic import BaseModel


class PlayerName(BaseModel):
    player_name: str


class RegionName(BaseModel):
    region_name: str


class RegionID(BaseModel):
    region_id: int


class DiscordVerifyInfo(BaseModel):
    discord_id: int
    player_name: str
    code: int


class ExportInfo(BaseModel):
    discord_id: int
    display_name: str
    file_type: str


class Bots(BaseModel):
    bot: int
    label: int
    names: list[str]
