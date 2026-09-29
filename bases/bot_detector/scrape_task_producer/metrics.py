import logging

from prometheus_client import Counter, start_http_server

logger = logging.getLogger(__name__)


def start_metrics_server(port: int) -> None:
    start_http_server(port)
    logger.info(f"metrics server started on port {port}")


lag_throttle_counter = Counter(
    name="scrape_task_producer_lag_throttles",
    documentation="Number of times producing paused due to kafka lag",
)

new_day_reset_counter = Counter(
    name="scrape_task_producer_new_day_resets",
    documentation="Number of fetch param resets on a new day",
)

done_for_day_counter = Counter(
    name="scrape_task_producer_done_for_day",
    documentation="Number of times the producer finished a full cycle for the day",
)

step_transition_counter = Counter(
    name="scrape_task_producer_step_transitions",
    documentation="Fetch step transitions in the producer loop",
    labelnames=["from_step", "to_step"],
)
