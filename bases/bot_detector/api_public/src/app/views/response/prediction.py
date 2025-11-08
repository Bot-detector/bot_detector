from datetime import datetime

from pydantic import BaseModel


class PredictionResponse(BaseModel):
    player_id: int
    player_name: str
    prediction_label: str
    prediction_confidence: float
    created: datetime
    predictions_breakdown: dict

    @classmethod
    def from_data(self, data: dict, breakdown: bool):
        # Create the player data dictionary with only the relevant fields
        prediction_data: dict = data.pop("predictions", {})
        player_data = {
            "player_id": data.pop("player_id"),
            "player_name": data.pop("name"),
            "created": data.pop("created_at"),
            "prediction_label": data.pop("prediction").lower(),
            "prediction_confidence": data.pop("confidence"),
            "predictions_breakdown": prediction_data if breakdown else {},
        }

        return self(**player_data)
