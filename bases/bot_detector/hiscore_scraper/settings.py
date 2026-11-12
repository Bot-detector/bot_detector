from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    METRICS_PORT: int = 8000
    # pipeline shape: kafka -> consume -> task_queue -> fetch pool ->
    # results_queue -> processors -> kafka
    # fetch slots are pure HTTP concurrency; throughput ~= slots / mean
    # fetch latency (Little's law). 1024 slots at a ~1.5s crawl-mix mean
    # is ~680/s, far below the per-proxy rate ceilings (20/s each).
    FETCH_CONCURRENCY: int = 1024
    PROCESS_CONCURRENCY: int = 8
    CONSUME_BATCH_SIZE: int = 200
    TASK_QUEUE_MAXSIZE: int = 2000
    RESULTS_QUEUE_MAXSIZE: int = 2000
    # one shared aiohttp session for the whole fetch pool; the connector
    # must cover the pool or aiohttp's default limit (100) binds first
    CONNECTION_LIMIT: int = 2048
