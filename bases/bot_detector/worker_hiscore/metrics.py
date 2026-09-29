import logging

from prometheus_client import Counter, start_http_server

logger = logging.getLogger(__name__)


def start_metrics_server(port: int) -> None:
    start_http_server(port)
    logger.info(f"metrics server started on port {port}")


rows_inserted_counter = Counter(
    name="worker_hiscore_rows_inserted",
    documentation="Number of highscore rows inserted",
)

players_updated_counter = Counter(
    name="worker_hiscore_players_updated",
    documentation="Number of players updated",
)
