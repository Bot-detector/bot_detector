from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    METRICS_PORT: int = 8000
