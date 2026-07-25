import logging
from collections.abc import AsyncGenerator
from typing import Any

from bot_detector.api_public.src.core.config import DB_SEMAPHORE, SETTINGS
from bot_detector.database import Settings as DBSettings
from bot_detector.database import get_session_factory
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)
# Reuse the shared database component instead of maintaining copy
_db_settings = DBSettings(
    DATABASE_URL=SETTINGS.DATABASE_URL,
    POOL_TIMEOUT=SETTINGS.POOL_TIMEOUT,
    POOL_RECYCLE=SETTINGS.POOL_RECYCLE,
    DB_DEBUG=SETTINGS.ENV != "PRD",
)

SessionFactory, _engine = get_session_factory(SETTINGS=_db_settings)


async def get_session() -> AsyncGenerator[AsyncSession, Any]:
    async with DB_SEMAPHORE, SessionFactory() as session:
        yield session
