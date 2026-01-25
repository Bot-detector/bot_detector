from ._metadata import MetaData
from .hiscore import (
    HighscoreBaseStruct,
    HighscoreDataBaseStruct,
    HighscoreDataDailyStruct,
    HighscoreDataLatestStruct,
    HighscoreDataMonthlyStruct,
    HighscoreDataWeeklyStruct,
)
from .player import PlayerStruct
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
    "PlayerStruct",
    "Detection",
    "ParsedDetection",
    "Equipment",
    "PredictionLatestRead",
    "PredictionBase",
    "PredictionCreate",
    "PredictionRead",
]
