import asyncio
import logging

from pydantic_settings import BaseSettings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    DATABASE_URL: str
    POOL_TIMEOUT: int = 25
    POOL_RECYCLE: int = 25
    DEBUG: bool = True
    DB_RETRY_ATTEMPTS: int = 10
    DB_RETRY_DELAY: float = 2.0


SETTINGS = Settings()

engine = create_async_engine(
    SETTINGS.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=90,
    pool_timeout=SETTINGS.POOL_TIMEOUT,
    pool_recycle=SETTINGS.POOL_RECYCLE,
    echo=SETTINGS.DEBUG,
)

Session = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def wait_for_db() -> None:
    for attempt in range(1, SETTINGS.DB_RETRY_ATTEMPTS + 1):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info("Database connection established")
            return
        except Exception as e:
            logger.warning(f"DB connection attempt {attempt}/{SETTINGS.DB_RETRY_ATTEMPTS} failed: {e}")
            if attempt < SETTINGS.DB_RETRY_ATTEMPTS:
                await asyncio.sleep(SETTINGS.DB_RETRY_DELAY)
            else:
                raise


class Base(DeclarativeBase):
    pass
