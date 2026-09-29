import logging
from typing import Literal

from prometheus_client import Counter, Gauge

logger = logging.getLogger(__name__)

QueueType = Literal["anonymous", "keyed"]

TYPE_ANONYMOUS: QueueType = "anonymous"
TYPE_KEYED: QueueType = "keyed"

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
    "messages delivered to a consumer group",
    ["topic", "type"],
)
FIREHOSE_BYTES = Counter(
    "firehose_bytes_total",
    "message payload bytes delivered to a consumer group",
    ["topic", "type"],
)
FIREHOSE_KICKED = Counter(
    "firehose_kicked_total",
    "connections kicked because their inbox was full",
    ["topic", "type"],
)


def stream_type(anonymous: bool) -> QueueType:
    return TYPE_ANONYMOUS if anonymous else TYPE_KEYED
