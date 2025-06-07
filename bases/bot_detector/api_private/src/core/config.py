from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ENV: str
    DATABASE_URL: str
    POOL_RECYCLE: int = 25
    POOL_TIMEOUT: int = 25


settings = Settings()
