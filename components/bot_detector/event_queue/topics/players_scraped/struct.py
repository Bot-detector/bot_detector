from bot_detector.structs._metadata import MetaData
from bot_detector.structs.hiscore import HighscoreBaseStruct
from bot_detector.structs.player import PlayerStruct
from pydantic import BaseModel


class ScrapedStruct(BaseModel):
    metadata: MetaData
    player_data: PlayerStruct
    highscore_data: HighscoreBaseStruct | None
