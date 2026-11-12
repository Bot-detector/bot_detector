from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    METRICS_PORT: int = 8000
    # fetch slots are pure HTTP concurrency; throughput ~= slots / mean
    # fetch latency (Little's law, crawl-mix mean ~1.43s). 1800 slots
    # on the 250-proxy pool is ~1250/s at ~5 req/s per proxy: half the
    # 20/s per-proxy budget, ~7 parallel connections per IP, leaving
    # headroom for retries, re-fetches and rotation windows.
    FETCH_CONCURRENCY: int = 1800
    PROCESS_CONCURRENCY: int = 16
    CONSUME_BATCH_SIZE: int = 200
    TASK_QUEUE_MAXSIZE: int = 2000
    RESULTS_QUEUE_MAXSIZE: int = 2000
    CONNECTION_LIMIT: int = 3600
