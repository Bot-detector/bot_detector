from .adapters.kafka import KafkaSettings as Settings
from .factory import QueueFactory
from .structs import (
    DataToPredictStruct,
    HighScoreStruct,
    NotFoundStruct,
    ReportsToInsertStruct,
    ScrapedStruct,
    ToScrapeStruct,
)

__all__ = [
    "QueueFactory",
    "Settings",
    "ToScrapeStruct",
    "ScrapedStruct",
    "NotFoundStruct",
    "ReportsToInsertStruct",
    "HighScoreStruct",
    "DataToPredictStruct",
]
