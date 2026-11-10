from collections.abc import Mapping

from bot_detector.event_queue.structs import (
    NotFoundStruct,
    PredictionsToInsertStruct,
    ReportsToInsertStruct,
    ScrapedStruct,
)
from bot_detector.firehose.core.config import TopicAccess
from pydantic import BaseModel

ANONYMOUS_CONSUMER_GROUP_PREFIX = "fh-anonymous"
KEYED_CONSUMER_GROUP_PREFIX = "fh"


# hardcoded catalog: topics exposed by the firehose -> message model
# (add entries here to expose more topics; each needs a `firehose.<topic>`
# permission for keyed access). anonymous visibility is not decided
# here: it comes from Settings.topic_access (see keyed_only_topics)
TOPIC_MODELS: dict[str, type[BaseModel]] = {
    "players.scraped": ScrapedStruct,
    "players.not_found": NotFoundStruct,
    "reports.to_insert": ReportsToInsertStruct,
    "predictions.to_insert": PredictionsToInsertStruct,
}

ALLOWED_TOPICS: list[str] = list(TOPIC_MODELS.keys())


def keyed_only_topics(topic_access: Mapping[str, TopicAccess]) -> frozenset[str]:
    """Topics streaming only to keyed identities (api key + scope).

    Everything else in the catalog is public: anonymous connects join
    the shared group. Unknown topics named in the map are rejected at
    startup (create_app), not here.
    """
    return frozenset(
        topic for topic, access in topic_access.items() if access == "keyed"
    )


def anonymous_topics(
    allowed_topics: list[str], keyed_only: frozenset[str]
) -> list[str]:
    """Catalog topics an unauthenticated caller may stream."""
    return [topic for topic in allowed_topics if topic not in keyed_only]
