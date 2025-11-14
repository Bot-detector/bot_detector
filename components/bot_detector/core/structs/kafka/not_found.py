from .._metadata import MetaData
from bot_detector.player.structs import PlayerStruct
from pydantic import BaseModel


class NotFoundStruct(BaseModel):
    metadata: MetaData
    player_data: PlayerStruct
