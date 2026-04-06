from datetime import datetime

from pydantic import BaseModel


class PredictionResponse(BaseModel):
    player_name: str
    prediction: float | None = None
    prediction_label: str | None = None
    created_at: datetime | None = None
