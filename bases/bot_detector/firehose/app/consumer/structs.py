from bot_detector.event_queue.structs import ReportsToInsertStruct, ScrapedStruct
from pydantic import BaseModel

ANONYMOUS_CONSUMER_GROUP_PREFIX = "fh-anonymous"
KEYED_CONSUMER_GROUP_PREFIX = "fh"


def report_ts(message: BaseModel) -> float | None:
    """Event timestamp (epoch seconds) of a reports.to_insert message."""
    ts = getattr(getattr(message, "report", None), "ts", None)
    if isinstance(ts, (int, float)) and not isinstance(ts, bool) and ts >= 0:
        return float(ts)
    return None


# hardcoded catalog: topics exposed by the firehose -> message model
# (add entries here to expose more topics; each needs a `firehose.<topic>`
# permission for keyed access)
TOPIC_MODELS: dict[str, type[BaseModel]] = {
    "players.scraped": ScrapedStruct,
    "reports.to_insert": ReportsToInsertStruct,
}

ALLOWED_TOPICS: list[str] = list(TOPIC_MODELS.keys())
