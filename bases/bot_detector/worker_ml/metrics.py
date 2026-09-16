import os

from prometheus_client import Counter, start_http_server

if os.environ.get("ENVIRONMENT") != "test":
    start_http_server(8000)

batches_consumed_counter = Counter(
    name="ml_worker_batches_consumed",
    documentation="Batches consumed from kafka by the ml worker",
    labelnames=["loop"],
)

predictions_inserted_counter = Counter(
    name="ml_worker_predictions_inserted",
    documentation="Number of predictions inserted into the database",
)

api_errors_counter = Counter(
    name="ml_worker_api_errors",
    documentation="Errors from the ml api during prediction",
    labelnames=["loop"],
)

messages_requeued_counter = Counter(
    name="ml_worker_messages_requeued",
    documentation="Messages requeued after failed processing",
    labelnames=["loop"],
)
