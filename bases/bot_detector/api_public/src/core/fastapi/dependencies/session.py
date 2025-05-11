from bot_detector.api_public.src.core.config import DB_SEMAPHORE
from bot_detector.api_public.src.core.database.database import SessionFactory
from sqlalchemy.ext.asyncio import AsyncSession


# Dependency to get an asynchronous session
async def get_session() -> AsyncSession:
    async with DB_SEMAPHORE:  # Acquire semaphore before accessing the session
        async with SessionFactory() as session:
            yield session  # Provide the session to the calling function
