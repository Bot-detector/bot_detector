from bot_detector.api_public.core.config import DB_SEMAPHORE, settings
from bot_detector.database import Settings as DBSettings
from bot_detector.database import get_session_factory
from sqlalchemy.ext.asyncio import AsyncSession

# Reuse the shared database component instead of maintaining copy
_db_settings = DBSettings(
    DATABASE_URL=settings.DATABASE_URL,
    POOL_TIMEOUT=settings.POOL_TIMEOUT,
    POOL_RECYCLE=settings.POOL_RECYCLE,
    DB_DEBUG=settings.ENV != "PRD",
)

SessionFactory, _engine = get_session_factory(SETTINGS=_db_settings)


async def get_session() -> AsyncSession:
    async with DB_SEMAPHORE:
        async with SessionFactory() as session:
            yield session
