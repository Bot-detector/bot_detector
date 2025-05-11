from ._metadata import MetaData
from .hiscore import (
    HighscoreBaseStruct,
    HighscoreDataBaseStruct,
    HighscoreDataDailyStruct,
    HighscoreDataMonthlyStruct,
    HighscoreDataWeeklyStruct,
)
from .kafka import NotFoundStruct, ReportsToInsertStruct, ScrapedStruct, ToScrapeStruct
from .player import PlayerStruct
from .reports import Detection, ParsedDetection

__all__ = [
    "MetaData",
    "HighscoreBaseStruct",
    "HighscoreDataBaseStruct",
    "HighscoreDataDailyStruct",
    "HighscoreDataWeeklyStruct",
    "HighscoreDataMonthlyStruct",
    "NotFoundStruct",
    "PlayerStruct",
    "ToScrapeStruct",
    "ScrapedStruct",
    "ReportsToInsertStruct",
    "Detection",
    "ParsedDetection",
]
