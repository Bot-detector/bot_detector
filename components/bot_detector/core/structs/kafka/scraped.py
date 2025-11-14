from bot_detector.highscore.structs import HighscoreBaseStruct
from bot_detector.player.structs import PlayerStruct
from pydantic import BaseModel

from .._metadata import MetaData


class ScrapedStruct(BaseModel):
    metadata: MetaData
    player_data: PlayerStruct
    highscore_data: HighscoreBaseStruct | None
