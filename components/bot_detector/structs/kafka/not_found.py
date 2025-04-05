from bot_detector.structs._metadata import MetaData
from bot_detector.structs.player import PlayerStruct
from pydantic import BaseModel


class NotFoundStruct(BaseModel):
    metadata: MetaData
    player_data: PlayerStruct
