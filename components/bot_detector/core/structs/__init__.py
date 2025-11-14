from ._metadata import MetaData
from .kafka import NotFoundStruct, ReportsToInsertStruct, ScrapedStruct, ToScrapeStruct

__all__ = [
    "MetaData",
    "NotFoundStruct",
    "ToScrapeStruct",
    "ScrapedStruct",
    "ReportsToInsertStruct",
]
