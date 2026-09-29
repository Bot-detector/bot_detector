import logging

from prometheus_client import Counter, Histogram, start_http_server

logger = logging.getLogger(__name__)


def start_metrics_server(port: int) -> None:
    start_http_server(port)
    logger.info(f"metrics server started on port {port}")


# Prometheus metrics
total_counter = Counter(
    name="runemetrics_scraper_requests",
    documentation="Count of request player stats fetches",
    labelnames=["proxy"],
)
success_counter = Counter(
    name="runemetrics_scraper_successes",
    documentation="Successful RuneMetrics requests",
    labelnames=["proxy"],
)
error_counter = Counter(
    name="runemetrics_scraper_errors",
    documentation="Errors in RuneMetrics requests",
    labelnames=["proxy"],
)
latency_histogram = Histogram(
    name="runemetrics_scraper_latency_seconds",
    documentation="Latency of RuneMetrics requests",
    labelnames=["proxy"],
    buckets=(
        0.05,
        0.075,
        0.1,
        0.25,
        0.5,
        0.75,
        1.0,
        2.5,
        5.0,
        7.5,
        10.0,
        20.0,
        30.0,
    ),
)

player_update_errors = Counter(
    name="runemetrics_scraper_player_update_errors",
    documentation="Count of errors during player update by error type",
    labelnames=["error_type"],
)

retry_counter = Counter(
    name="runemetrics_scraper_retries",
    documentation="Cumulative count of retry attempts",
    labelnames=["proxy"],
)
retry_histogram = Histogram(
    name="runemetrics_scraper_retry_consecutive_failures",
    documentation="Distribution of consecutive failure counts",
    labelnames=["proxy"],
    buckets=(1, 2, 3, 5, 10, 15, 20, 30, 50),
)
retry_delay_histogram = Histogram(
    name="runemetrics_scraper_retry_backoff_seconds",
    documentation="Distribution of backoff delays applied",
    labelnames=["proxy"],
    buckets=(10, 20, 40, 80, 120, 160, 200, 250, 300),
)
