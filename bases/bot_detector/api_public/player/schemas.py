from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator


class PlayerCreate(BaseModel):
    name: str
    possible_ban: Optional[bool] = 0
    confirmed_ban: Optional[bool] = 0
    confirmed_player: Optional[bool] = 0
    label_id: Optional[int] = 0
    label_jagex: Optional[int] = 0
    ironman: Optional[int] = None
    hardcore_ironman: Optional[int] = None
    ultimate_ironman: Optional[int] = None
    normalized_name: Optional[str] = None


class PlayerUpdate(BaseModel):
    name: Optional[str] = None
    possible_ban: Optional[bool] = None
    confirmed_ban: Optional[bool] = None
    confirmed_player: Optional[bool] = None
    label_id: Optional[int] = None
    label_jagex: Optional[int] = None
    ironman: Optional[int] = None
    hardcore_ironman: Optional[int] = None
    ultimate_ironman: Optional[int] = None
    normalized_name: Optional[str] = None


class PlayerInDB(PlayerCreate):
    id: int
    created_at: datetime
    updated_at: datetime | None

    @field_validator("created_at", mode="before")
    def parse_created_at(cls, value):
        if isinstance(value, str):
            return datetime.fromisoformat(value)
        if value is None:
            raise ValueError("created_at cannot be None")
        return value


class Player(PlayerInDB):
    pass


class PlayerResponse(BaseModel):
    id: int
    name: str
    created_at: datetime
    updated_at: datetime
    possible_ban: bool
    confirmed_ban: bool
    confirmed_player: bool
    label_id: int
    label_jagex: int
    ironman: bool
    hardcore_ironman: bool
    ultimate_ironman: bool
    normalized_name: str


class ReportScoreResponse(BaseModel):
    count: int
    possible_ban: bool
    confirmed_ban: bool
    confirmed_player: bool
    manual_detect: bool


class FeedbackScoreResponse(BaseModel):
    count: int
    possible_ban: bool
    confirmed_ban: bool
    confirmed_player: bool


class PredictionResponse(BaseModel):
    player_id: int
    player_name: str
    prediction_label: str
    prediction_confidence: float
    created: datetime
    predictions_breakdown: dict

    @classmethod
    def from_data(cls, data: dict, breakdown: bool):
        prediction_data: dict = data.pop("predictions", {})
        player_data = {
            "player_id": data.pop("player_id"),
            "player_name": data.pop("name"),
            "created": data.pop("created_at"),
            "prediction_label": data.pop("prediction").lower(),
            "prediction_confidence": data.pop("confidence"),
            "predictions_breakdown": prediction_data if breakdown else {},
        }
        return cls(**player_data)
