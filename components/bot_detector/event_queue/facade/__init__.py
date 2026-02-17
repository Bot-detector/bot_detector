from bot_detector.event_queue.structs import (
    DataToPredictStruct,
    HighScoreStruct,
    NotFoundStruct,
    ReportsToInsertStruct,
    ScrapedStruct,
    ToScrapeStruct,
)

from .data_to_predict import (
    DataToPredictConsumer,
    DataToPredictProducer,
    DataToPredictQueue,
)
from .players_not_found import (
    PlayersNotFoundConsumer,
    PlayersNotFoundProducer,
    PlayersNotFoundQueue,
)
from .players_scraped import (
    PlayersScrapedConsumer,
    PlayersScrapedProducer,
    PlayersScrapedQueue,
)
from .players_to_scrape import (
    PlayersToScrapeConsumer,
    PlayersToScrapeProducer,
    PlayersToScrapeQueue,
)
from .reports_to_insert import (
    ReportsToInsertConsumer,
    ReportsToInsertProducer,
    ReportsToInsertQueue,
)
from .settings import Settings

__all__ = [
    "Settings",
    "ToScrapeStruct",
    "ScrapedStruct",
    "NotFoundStruct",
    "ReportsToInsertStruct",
    "HighScoreStruct",
    "DataToPredictStruct",
    "PlayersToScrapeProducer",
    "PlayersToScrapeConsumer",
    "PlayersToScrapeQueue",
    "PlayersScrapedProducer",
    "PlayersScrapedConsumer",
    "PlayersScrapedQueue",
    "PlayersNotFoundProducer",
    "PlayersNotFoundConsumer",
    "PlayersNotFoundQueue",
    "ReportsToInsertProducer",
    "ReportsToInsertConsumer",
    "ReportsToInsertQueue",
    "DataToPredictProducer",
    "DataToPredictConsumer",
    "DataToPredictQueue",
]
