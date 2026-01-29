import os

from prometheus_client import Counter, Histogram, start_http_server

if os.environ.get("ENVIRONMENT") != "test":
    start_http_server(8000)

# Prometheus metrics
total_counter = Counter(
    name="highscore_request_count",
    documentation="Count of request player stats fetches",
    labelnames=["proxy"],
)
success_counter = Counter(
    name="highscore_success_count",
    documentation="Count of successful player stats fetches",
    labelnames=["proxy"],
)
error_counter = Counter(
    name="highscore_error_count",
    documentation="Count of failed player stats fetches",
    labelnames=["proxy"],
)
not_found_counter = Counter(
    name="highscore_not_found_count",
    documentation="Count of players not found",
    labelnames=["proxy"],
)
latency_histogram = Histogram(
    name="highscore_fetch_latency_seconds",
    documentation="Latency of player stats fetches",
    labelnames=["proxy"],
    buckets=(0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0, 20.0, 30.0),
)
