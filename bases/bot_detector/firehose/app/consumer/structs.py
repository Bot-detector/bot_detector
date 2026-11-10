from bot_detector.event_queue.structs import (
    NotFoundStruct,
    PredictionsToInsertStruct,
    ReportsToInsertStruct,
    ScrapedStruct,
)
from pydantic import BaseModel

ANONYMOUS_CONSUMER_GROUP_PREFIX = "fh-anonymous"
KEYED_CONSUMER_GROUP_PREFIX = "fh"


# hardcoded catalog: topics exposed by the firehose -> message model
# (add entries here to expose more topics; each needs a `firehose.<topic>`
# permission for keyed access)
TOPIC_MODELS: dict[str, type[BaseModel]] = {
    "players.scraped": ScrapedStruct,
    "players.not_found": NotFoundStruct,
    "reports.to_insert": ReportsToInsertStruct,
    "predictions.to_insert": PredictionsToInsertStruct,
}

ALLOWED_TOPICS: list[str] = list(TOPIC_MODELS.keys())
