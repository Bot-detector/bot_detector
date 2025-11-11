from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


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


class PlayerStruct(PlayerCreate):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None


class PlayerInDB(PlayerCreate):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    @field_validator("created_at", mode="before")
    def parse_created_at(cls, value: Any):
        if isinstance(value, str):
            return datetime.fromisoformat(value)
        if value is None:
            raise ValueError("created_at cannot be None")
        return value


class PlayerResponse(PlayerInDB):
    pass


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
        player_data = {
            "player_id": data.pop("id"),
            "player_name": data.pop("name"),
            "prediction_label": data.pop("prediction").lower(),
            "prediction_confidence": data.pop("predicted_confidence") / 100.0,
            "created": data.pop("created"),
            "predictions_breakdown": (
                {k: v / 100.0 if v > 0 else v for k, v in data.items()}
                if breakdown
                else {}
            ),
        }
        return cls(**player_data)
