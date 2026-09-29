import logging

from prometheus_client import Counter, Histogram, start_http_server

logger = logging.getLogger(__name__)


def start_metrics_server(port: int) -> None:
    start_http_server(port)
    logger.info(f"metrics server started on port {port}")


# Prometheus metrics
total_counter = Counter(
    name="hiscore_scraper_requests",
    documentation="Count of request player stats fetches",
    labelnames=["proxy"],
)
success_counter = Counter(
    name="hiscore_scraper_successes",
    documentation="Count of successful player stats fetches",
    labelnames=["proxy"],
)
error_counter = Counter(
    name="hiscore_scraper_errors",
    documentation="Count of failed player stats fetches",
    labelnames=["proxy"],
)
not_found_counter = Counter(
    name="hiscore_scraper_not_found",
    documentation="Count of players not found",
    labelnames=["proxy"],
)
latency_histogram = Histogram(
    name="hiscore_scraper_fetch_latency_seconds",
    documentation="Latency of player stats fetches",
    labelnames=["proxy"],
    buckets=(0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0, 20.0, 30.0),
)

# Retry tracking metrics
retry_counter = Counter(
    name="hiscore_scraper_retries",
    documentation="Count of retry attempts (cumulative)",
    labelnames=["proxy"],
)
retry_histogram = Histogram(
    name="hiscore_scraper_retry_consecutive_failures",
    documentation="Distribution of consecutive failure counts before success",
    labelnames=["proxy"],
    buckets=(1, 2, 3, 5, 10, 15, 20, 30, 50),
)
retry_delay_histogram = Histogram(
    name="hiscore_scraper_retry_backoff_seconds",
    documentation="Distribution of backoff delays applied",
    labelnames=["proxy"],
    buckets=(10, 20, 40, 80, 120, 160, 200, 250, 300),
)
