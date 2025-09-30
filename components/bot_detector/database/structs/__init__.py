from .hiscore import (
    HighscoreDataDailyTableStruct,
    HighscoreDataLatestTableStruct,
    HighscoreDataMonthlyTableStruct,
    HighscoreDataWeeklyTableStruct,
)
from .player import PlayersTableStruct
from .prediction import PredictionLatestStruct, PredictionStruct

__all__ = [
    "PlayersTableStruct",
    "HighscoreDataDailyTableStruct",
    "HighscoreDataMonthlyTableStruct",
    "HighscoreDataWeeklyTableStruct",
    "HighscoreDataLatestTableStruct",
    "PredictionLatestStruct",
    "PredictionStruct",
]
