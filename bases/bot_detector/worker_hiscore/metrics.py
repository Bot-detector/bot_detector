import os

from prometheus_client import Counter, start_http_server

if os.environ.get("ENVIRONMENT") != "test":
    start_http_server(8000)

rows_inserted_counter = Counter(
    name="highscore_worker_rows_inserted",
    documentation="Number of highscore rows inserted",
)

players_updated_counter = Counter(
    name="highscore_worker_players_updated",
    documentation="Number of players updated",
)

to_predict_produced_counter = Counter(
    name="highscore_worker_to_predict_produced",
    documentation="Number of records produced to data.to_predict",
)
