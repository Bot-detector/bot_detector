import logging

from prometheus_client import Counter, start_http_server

logger = logging.getLogger(__name__)


def start_metrics_server(port: int) -> None:
    start_http_server(port)
    logger.info(f"metrics server started on port {port}")


batches_consumed_counter = Counter(
    name="worker_ml_batches_consumed",
    documentation="Batches consumed from kafka by the ml worker",
    labelnames=["loop"],
)

predictions_published_counter = Counter(
    name="worker_ml_predictions_published",
    documentation="Number of predictions published to kafka",
)

api_errors_counter = Counter(
    name="worker_ml_api_errors",
    documentation="Errors from the ml api during prediction",
    labelnames=["loop"],
)

messages_requeued_counter = Counter(
    name="worker_ml_messages_requeued",
    documentation="Messages requeued after failed processing",
    labelnames=["loop"],
)
