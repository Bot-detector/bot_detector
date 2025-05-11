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

        return self(**player_data)
