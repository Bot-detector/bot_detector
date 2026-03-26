from pydantic_settings import BaseSettings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Settings(BaseSettings):
    DATABASE_URL: str
    POOL_TIMEOUT: int = 25
    POOL_RECYCLE: int = 25
    DEBUG: bool = True


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


class Base(DeclarativeBase):
    pass
