import logging

from prometheus_client import Counter, Histogram

logger = logging.getLogger(__name__)


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
