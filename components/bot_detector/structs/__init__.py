from ._metadata import MetaData
from .hiscore import (
    HighscoreBaseStruct,
    HighscoreDataBaseStruct,
    HighscoreDataDailyStruct,
    HighscoreDataLatestStruct,
    HighscoreDataMonthlyStruct,
    HighscoreDataWeeklyStruct,
)
from .kafka import NotFoundStruct, ReportsToInsertStruct, ScrapedStruct, ToScrapeStruct
from .player import PlayerStruct
from .reports import Detection, Equipment, ParsedDetection

__all__ = [
    "MetaData",
    "HighscoreBaseStruct",
    "HighscoreDataLatestStruct",
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
    "Equipment",
]
