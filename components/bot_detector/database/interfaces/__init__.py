from .hiscore import (
    HighscoreDataDailyInterface,
    HighscoreDataLatestInterface,
    HighscoreDataMonthlyInterface,
    HighscoreDataWeeklyInterface,
)
from .player import playerInterface
from .prediction import PredictionInterface, PredictionLatestInterface
from .report import ReportInterface

__all__ = [
    "playerInterface",
    "HighscoreDataLatestInterface",
    "HighscoreDataDailyInterface",
    "HighscoreDataWeeklyInterface",
    "HighscoreDataMonthlyInterface",
    "ReportInterface",
    "PredictionLatestInterface",
    "PredictionInterface",
]
