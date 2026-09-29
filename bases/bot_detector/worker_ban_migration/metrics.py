import logging

from prometheus_client import Counter, start_http_server

logger = logging.getLogger(__name__)


def start_metrics_server(port: int) -> None:
    start_http_server(port)
    logger.info(f"metrics server started on port {port}")


accounts_migrated_counter = Counter(
    name="worker_ban_migration_accounts_migrated",
    documentation="Number of banned accounts whose reports were migrated",
)

rows_migrated_counter = Counter(
    name="worker_ban_migration_rows_migrated",
    documentation="Number of report_archive rows inserted by the ban migration worker",
)
