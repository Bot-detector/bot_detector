# conftest.py
import os
import sys
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from httpx._transports.asgi import ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from src.core import server  # noqa: E402
from src.core.fastapi.dependencies.session import get_session  # noqa: E402


# Create an async SQLAlchemy engine
async def get_session_override():
    engine = create_async_engine(
        "mysql+aiomysql://root:root_bot_buster@localhost:3307/playerdata",
        pool_timeout=30,
        pool_recycle=30,
        echo=True,
        pool_pre_ping=True,
    )

    # Create a session factory
    SessionFactory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
        class_=AsyncSession,  # Use AsyncSession for asynchronous operations
    )
    async with SessionFactory() as session:
        session: AsyncSession
        yield session
    await engine.dispose()
    return


server.app.dependency_overrides[get_session] = get_session_override


@pytest.fixture
def app() -> FastAPI:
    return server.app


@pytest.fixture
@asynccontextmanager
async def custom_client(app: FastAPI):
    base_url = "http://srv.test/"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url=base_url) as client:
        yield client
