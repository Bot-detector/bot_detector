import logging
import os

from prometheus_client import Counter, Histogram, start_http_server

logger = logging.getLogger(__name__)

_started = False

WORKER_LABELS = ["worker"]


def start_metrics_server(port: int = 8000) -> None:
    """Start the Prometheus metrics HTTP server.

    Idempotent: subsequent calls are no-ops. No-op when ENVIRONMENT == "test"
    so unit tests don't bind a port.
    """
    global _started
    if _started:
        return
    if os.environ.get("ENVIRONMENT") == "test":
        return
    start_http_server(port)
    _started = True
    logger.info(f"Metrics server listening on :{port}")


messages_consumed_counter = Counter(
    name="worker_messages_consumed_total",
    documentation="Total messages pulled from the queue by WorkerRunner",
    labelnames=WORKER_LABELS,
)
messages_committed_counter = Counter(
    name="worker_messages_committed_total",
    documentation="Total messages successfully committed (processed)",
    labelnames=WORKER_LABELS,
)
messages_requeued_counter = Counter(
    name="worker_messages_requeued_total",
    documentation="Total messages requeued, by reason",
    labelnames=["worker", "reason"],
)
batch_size_histogram = Histogram(
    name="worker_batch_size",
    documentation="Distribution of consumed batch sizes",
    labelnames=WORKER_LABELS,
)
handle_duration_histogram = Histogram(
    name="worker_handle_duration_seconds",
    documentation="Wall-clock time spent in Worker.handle() per batch",
    labelnames=WORKER_LABELS,
)
batch_errors_counter = Counter(
    name="worker_batch_errors_total",
    documentation="Exceptions raised inside handle(), by exception type",
    labelnames=["worker", "error_type"],
)
poll_idle_counter = Counter(
    name="worker_poll_idle_total",
    documentation="Empty polls where no messages were available",
    labelnames=WORKER_LABELS,
)
