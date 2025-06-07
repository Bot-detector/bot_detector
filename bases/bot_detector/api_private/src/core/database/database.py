from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from src.core.config import settings

# Create an async SQLAlchemy engine
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_timeout=settings.POOL_TIMEOUT,
    pool_recycle=settings.POOL_RECYCLE,
    echo=(settings.ENV != "PRD"),
    pool_pre_ping=True,
)

# Create a session factory
SessionFactory = sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,  # Use AsyncSession for asynchronous operations
)

Base = declarative_base()
