from .._metadata import MetaData
from bot_detector.highscore_worker.structs import HighscoreBaseStruct
from bot_detector.player.structs import PlayerStruct
from pydantic import BaseModel


class ScrapedStruct(BaseModel):
    metadata: MetaData
    player_data: PlayerStruct
    highscore_data: HighscoreBaseStruct | None
