from ._metadata import MetaData
from .hiscore import (
    HighscoreBaseStruct,
    HighscoreDataBaseStruct,
    HighscoreDataDailyStruct,
    HighscoreDataMonthlyStruct,
    HighscoreDataWeeklyStruct,
)
from .kafka import NotFoundStruct, ScrapedStruct, ToScrapeStruct
from .player import PlayerStruct

__all__ = [
    "HighscoreBaseStruct",
    "HighscoreDataBaseStruct",
    "HighscoreDataDailyStruct",
    "HighscoreDataWeeklyStruct",
    "HighscoreDataMonthlyStruct",
    "NotFoundStruct",
    "PlayerStruct",
    "ToScrapeStruct",
    "ScrapedStruct",
    "MetaData",
]
