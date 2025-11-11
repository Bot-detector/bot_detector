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
from .player import (
    FeedbackScoreResponse,
    PlayerCreate,
    PlayerInDB,
    PlayerResponse,
    PlayerStruct,
    PredictionResponse,
    ReportScoreResponse,
)
from .prediction import (
    PredictionBase,
    PredictionCreate,
    PredictionLatestRead,
    PredictionRead,
)
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
    "PlayerCreate",
    "PlayerInDB",
    "PlayerResponse",
    "PlayerStruct",
    "PredictionResponse",
    "ReportScoreResponse",
    "FeedbackScoreResponse",
    "ToScrapeStruct",
    "ScrapedStruct",
    "ReportsToInsertStruct",
    "Detection",
    "ParsedDetection",
    "Equipment",
    "PredictionLatestRead",
    "PredictionBase",
    "PredictionCreate",
    "PredictionRead",
]
