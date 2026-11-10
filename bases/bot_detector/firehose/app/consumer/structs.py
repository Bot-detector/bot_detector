from bot_detector.event_queue.structs import (
    NotFoundStruct,
    PredictionsToInsertStruct,
    ScrapedStruct,
)
from pydantic import BaseModel

ANONYMOUS_CONSUMER_GROUP_PREFIX = "fh-anonymous"
KEYED_CONSUMER_GROUP_PREFIX = "fh"


# hardcoded catalog: topics exposed by the firehose -> message model
# (add entries here to expose more topics; each needs a `firehose.<topic>`
# permission for keyed access)
#
# reports.to_insert is disabled: left out of the catalog, so
# /firehose/topics stops advertising it and websocket connects close
# 4404 before auth or a kafka consumer is created. its 2h emission
# delay stays configured in queue_manager.TOPIC_HOLDS, so re-enabling
# is a one-line change here.
TOPIC_MODELS: dict[str, type[BaseModel]] = {
    "players.scraped": ScrapedStruct,
    "players.not_found": NotFoundStruct,
    "predictions.to_insert": PredictionsToInsertStruct,
}

ALLOWED_TOPICS: list[str] = list(TOPIC_MODELS.keys())
