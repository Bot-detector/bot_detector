from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROXY_API_KEY: str
    MAX_CALLS: int = 100
    INTERVAL: int = 60
