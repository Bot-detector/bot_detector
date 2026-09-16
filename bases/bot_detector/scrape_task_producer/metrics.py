import os

from prometheus_client import Counter, start_http_server

if os.environ.get("ENVIRONMENT") != "test":
    start_http_server(8000)

players_produced_counter = Counter(
    name="scrape_task_producer_players_produced",
    documentation="Number of players produced to players.to_scrape",
)

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
