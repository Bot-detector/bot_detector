import asyncio

from dotenv import find_dotenv, load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings

load_dotenv(find_dotenv())


class Settings(BaseSettings):
    ENV: str = Field(default="DEV")
    DATABASE_URL: str = Field(default=...)
    KAFKA_BOOTSTRAP_SERVERS: str = Field(default=...)
    POOL_RECYCLE: int = Field(default=60)
    POOL_TIMEOUT: int = Field(default=60)
    KAFKA_MAX_ASYNC_CALLS: int = Field(default=100)


SETTINGS = Settings()

DB_SEMAPHORE = asyncio.Semaphore(100)
