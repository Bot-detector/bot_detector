import logging

from bot_detector.rate_limiter import WaitEvent
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
fetch_outcome_latency_histogram = Histogram(
    name="hiscore_scraper_fetch_outcome_latency_seconds",
    documentation="Latency of player stats fetches by outcome (success/not_found/error)",
    labelnames=["proxy", "outcome"],
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

# Rate limiter metrics
rate_limited_counter = Counter(
    name="hiscore_scraper_rate_limited",
    documentation="Calls delayed because a rate limit window was exhausted",
    labelnames=["window"],
)
rate_limit_sleep_histogram = Histogram(
    name="hiscore_scraper_rate_limit_sleep_seconds",
    documentation="Seconds the scraper waited for a rate limit window to free up",
    labelnames=["window"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)


def on_rate_limit_wait(event: WaitEvent) -> None:
    """Records a rate limiter wait as metrics."""
    for window in event.blocked:
        rate_limited_counter.labels(window=window.name).inc()
    rate_limit_sleep_histogram.labels(window=event.binding.name).observe(event.wait_s)
