import os

from prometheus_client import Counter, start_http_server

if os.environ.get("ENVIRONMENT") != "test":
    start_http_server(8000)

reports_inserted_counter = Counter(
    name="report_worker_reports_inserted",
    documentation="Number of report rows inserted",
)

reports_dropped_counter = Counter(
    name="report_worker_reports_dropped",
    documentation="Number of reports dropped as invalid during transformation",
)
