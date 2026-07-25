from bot_detector.database.prediction.structs import (
    PredictionLatestStruct as Prediction_v2,
)

from .feedback import FeedbackRepo, PredictionFeedback
from .label import Label, LabelRepo
from .player import Player, PlayerRepo
from .prediction import Prediction_v1
from .report import Report

__all__ = [
    "FeedbackRepo",
    "Label",
    "LabelRepo",
    "Player",
    "PlayerRepo",
    "PredictionFeedback",
    "Prediction_v1",
    "Prediction_v2",
    "Report",
]
