from bot_detector.api_public.src.core.database.database import SessionFactory
from sqlalchemy.ext.asyncio import AsyncSession


# Dependency to get an asynchronous session
async def get_session() -> AsyncSession:
    async with SessionFactory() as session:
        yield session
