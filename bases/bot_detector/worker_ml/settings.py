from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    BASE_URL: str = Field(default=...)
    MAX_MESSAGES: int = Field(default=100)
    MAX_INTERVAL_MS: int = Field(default=5000)


SETTINGS = Settings()
