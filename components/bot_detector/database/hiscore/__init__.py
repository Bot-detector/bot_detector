from .interface import HighscoreDataLatestInterface
from .repository import HighscoreDataRepo
from .structs import (
    HighscoreDataDailyTableStruct,
    HighscoreDataLatestTableStruct,
    HighscoreDataMonthlyTableStruct,
    HighscoreDataWeeklyTableStruct,
)

__all__ = [
    "HighscoreDataLatestInterface",
    "HighscoreDataRepo",
    "HighscoreDataLatestTableStruct",
    "HighscoreDataDailyTableStruct",
    "HighscoreDataWeeklyTableStruct",
    "HighscoreDataMonthlyTableStruct",
]
