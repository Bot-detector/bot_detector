import logging

from prometheus_client import Counter, start_http_server

logger = logging.getLogger(__name__)


def start_metrics_server(port: int) -> None:
    start_http_server(port)
    logger.info(f"metrics server started on port {port}")


predictions_inserted_counter = Counter(
    name="worker_prediction_predictions_inserted",
    documentation="Number of predictions inserted into the database",
)
