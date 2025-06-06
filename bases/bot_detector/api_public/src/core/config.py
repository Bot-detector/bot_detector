import asyncio
import sys

from dotenv import find_dotenv, load_dotenv
from pydantic_settings import BaseSettings

if "pytest" in sys.modules:
    load_dotenv(find_dotenv(".env.test"))
else:
    load_dotenv(find_dotenv())  # fallback to normal .env


class Settings(BaseSettings):
    ENV: str = "DEV"
    DATABASE_URL: str
    KAFKA_BOOTSTRAP_SERVERS: str
    POOL_RECYCLE: int = 60
    POOL_TIMEOUT: int = 60


settings = Settings()

DB_SEMAPHORE = asyncio.Semaphore(100)
