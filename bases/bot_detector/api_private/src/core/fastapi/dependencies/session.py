from sqlalchemy.ext.asyncio import AsyncSession

from bases.bot_detector.api_private.src.core.database.database import SessionFactory


# Dependency to get an asynchronous session
async def get_session() -> AsyncSession:
    async with SessionFactory() as session:
        yield session
