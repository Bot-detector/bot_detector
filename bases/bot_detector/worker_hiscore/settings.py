from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    N_WORKERS: int = 1
    MAX_BATCH_SIZE: int = 10_000
    MAX_INTERVAL_MS: int = 5_000
    METRICS_PORT: int = 8000
