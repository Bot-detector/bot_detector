from dotenv import find_dotenv, load_dotenv
from pydantic_settings import BaseSettings

load_dotenv(find_dotenv())


class Settings(BaseSettings):
    ENV: str = "DEV"
    DATABASE_URL: str
    KAFKA_BOOTSTRAP_SERVERS: str
    POOL_RECYCLE: int = 30
    POOL_TIMEOUT: int = 30


settings = Settings()
