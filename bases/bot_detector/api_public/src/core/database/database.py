from bot_detector.api_public.src.core.config import settings
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Create an async SQLAlchemy engine
from sqlalchemy.pool import StaticPool  # add at the top with your imports

# Create an async SQLAlchemy engine
if settings.DATABASE_URL.startswith("sqlite"):
    engine = create_async_engine(
        settings.DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=(settings.ENV != "PRD"),
    )
else:
    engine = create_async_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=90,
        pool_timeout=settings.POOL_TIMEOUT,
        pool_recycle=settings.POOL_RECYCLE,
        echo=(settings.ENV != "PRD"),
    )

# Create a session factory
SessionFactory = sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,  # Use AsyncSession for asynchronous operations
)

Base = declarative_base()
