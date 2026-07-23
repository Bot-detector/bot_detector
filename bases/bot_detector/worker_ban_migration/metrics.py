import os

from prometheus_client import Counter, start_http_server

if os.environ.get("ENVIRONMENT") != "test":
    start_http_server(8000)

# Prometheus metrics
accounts_migrated_counter = Counter(
    name="ban_migration_accounts_migrated",
    documentation="Number of banned accounts whose reports were migrated",
)

rows_migrated_counter = Counter(
    name="ban_migration_rows_migrated",
    documentation="Number of report_archive rows inserted by the ban migration worker",
)
