import asyncio

from dotenv import find_dotenv, load_dotenv
from pydantic_settings import BaseSettings

load_dotenv(find_dotenv())


class Settings(BaseSettings):
    ENV: str = "DEV"
    DATABASE_URL: str
    KAFKA_BOOTSTRAP_SERVERS: str
    POOL_RECYCLE: int = 60
    POOL_TIMEOUT: int = 60
    KAFKA_MAX_ASYNC_CALLS: int = 100


settings = Settings()

DB_SEMAPHORE = asyncio.Semaphore(100)
