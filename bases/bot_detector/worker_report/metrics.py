import logging

from prometheus_client import Counter, start_http_server

logger = logging.getLogger(__name__)


def start_metrics_server(port: int) -> None:
    start_http_server(port)
    logger.info(f"metrics server started on port {port}")


reports_inserted_counter = Counter(
    name="worker_report_reports_inserted",
    documentation="Number of report rows inserted",
)

reports_dropped_counter = Counter(
    name="worker_report_reports_dropped",
    documentation="Number of reports dropped as invalid during transformation",
)
