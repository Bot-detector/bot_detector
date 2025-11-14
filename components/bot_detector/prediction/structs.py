from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class PredictionBase(BaseModel):
    model_name: str = Field(..., max_length=50)
    prediction: str = Field(..., max_length=50)
    confidence: float
    predictions: Optional[dict[str, Any]] = None


class PredictionCreate(PredictionBase):
    player_id: int


class PredictionRead(PredictionBase):
    prediction_id: int
    player_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class PredictionLatestRead(PredictionBase):
    player_id: int
    created_at: datetime

    class Config:
        from_attributes = True


__all__ = [
    "PredictionBase",
    "PredictionCreate",
    "PredictionRead",
    "PredictionLatestRead",
]
