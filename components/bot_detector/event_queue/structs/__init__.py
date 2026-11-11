from .data_to_predict import DataToPredictStruct, HighScoreStruct
from .name_mapper import ACTIVITY_NAME_TO_FIELD, map_highscore_keys
from .players_banned import PlayerBannedStruct
from .players_not_found import NotFoundStruct
from .players_scraped import ScrapedStruct
from .players_to_scrape import ToScrapeBatchStruct, ToScrapeMessage, ToScrapeStruct
from .predictions_to_insert import PredictionsToInsertStruct
from .reports_to_insert import ReportsToInsertStruct

__all__ = [
    "ToScrapeStruct",
    "ToScrapeBatchStruct",
    "ToScrapeMessage",
    "ScrapedStruct",
    "NotFoundStruct",
    "ReportsToInsertStruct",
    "HighScoreStruct",
    "DataToPredictStruct",
    "PlayerBannedStruct",
    "PredictionsToInsertStruct",
    "ACTIVITY_NAME_TO_FIELD",
    "map_highscore_keys",
]
