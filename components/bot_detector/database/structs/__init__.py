from .feedback import PredictionsFeedbackTableStruct
from .hiscore import (
    HighscoreDataDailyTableStruct,
    HighscoreDataLatestTableStruct,
    HighscoreDataMonthlyTableStruct,
    HighscoreDataWeeklyTableStruct,
)
from .label import LabelsTableStruct
from .player import PlayersTableStruct
from .prediction import (
    PredictionLatestStruct,
    PredictionStruct,
    PredictionsTableStruct,
)
from .report import ReportsTableStruct

__all__ = [
    "PlayersTableStruct",
    "LabelsTableStruct",
    "HighscoreDataDailyTableStruct",
    "HighscoreDataMonthlyTableStruct",
    "HighscoreDataWeeklyTableStruct",
    "HighscoreDataLatestTableStruct",
    "PredictionLatestStruct",
    "PredictionStruct",
    "PredictionsTableStruct",
    "PredictionsFeedbackTableStruct",
    "ReportsTableStruct",
]
