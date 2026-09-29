import logging

from prometheus_client import Counter, Gauge

logger = logging.getLogger(__name__)

TYPE_ANONYMOUS = "anonymous"
TYPE_KEYED = "keyed"

FIREHOSE_CONSUMERS = Gauge(
    "firehose_consumers",
    "active kafka consumers",
    ["topic", "type"],
)
FIREHOSE_CONNECTIONS = Gauge(
    "firehose_connections",
    "active websocket connections",
    ["topic", "type"],
)
FIREHOSE_MESSAGES = Counter(
    "firehose_messages_total",
    "messages delivered to connections",
    ["topic", "type"],
)
FIREHOSE_BYTES = Counter(
    "firehose_bytes_total",
    "message payload bytes delivered to connections",
    ["topic", "type"],
)
FIREHOSE_DROPPED = Counter(
    "firehose_dropped_total",
    "oldest messages evicted from a slow anonymous connection's inbox",
    ["topic", "type"],
)


def stream_type(anonymous: bool) -> str:
    return TYPE_ANONYMOUS if anonymous else TYPE_KEYED
