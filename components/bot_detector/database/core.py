from pydantic import Field
from pydantic_settings import BaseSettings
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass


class Settings(BaseSettings):
    DATABASE_URL: str = Field(default=...)
    POOL_TIMEOUT: int = 25
    POOL_RECYCLE: int = 25
    DB_DEBUG: bool = False


class Base(MappedAsDataclass, DeclarativeBase):
    """subclasses will be converted to dataclasses"""


def get_session_factory(
    SETTINGS: Settings,
) -> tuple[async_sessionmaker[AsyncSession], AsyncEngine]:
    async_engine = create_async_engine(
        SETTINGS.DATABASE_URL,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=90,
        pool_timeout=SETTINGS.POOL_TIMEOUT,
        pool_recycle=SETTINGS.POOL_RECYCLE,
        echo=SETTINGS.DB_DEBUG,
    )
    async_session = async_sessionmaker(
        bind=async_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    return async_session, async_engine
