from bot_detector.structs._metadata import MetaData
from pydantic import BaseModel


class PlayerBannedStruct(BaseModel):
    metadata: MetaData
    player_id: int
    name: str
