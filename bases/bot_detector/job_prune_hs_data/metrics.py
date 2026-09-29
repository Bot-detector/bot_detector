import logging

from prometheus_client import Counter, start_http_server

logger = logging.getLogger(__name__)


def start_metrics_server(port: int) -> None:
    start_http_server(port)
    logger.info(f"metrics server started on port {port}")


rows_deleted_counter = Counter(
    name="job_prune_hs_data_rows_deleted",
    documentation="Number of highscore_data_daily rows deleted",
)
