import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI

from bases.api_public.core import server
from bases.api_public.core.fastapi.dependencies import session as session_dep
from bases.api_public.core.fastapi.dependencies import kafka as kafka_dep


def test_create_app_wires_routes_and_middleware():
    app = server.create_app()
    assert isinstance(app, FastAPI)
    paths = {route.path for route in app.routes}
    assert "/v2/player/prediction" in paths
    middleware_names = {mw.cls.__name__ for mw in app.user_middleware}
    assert {"LoggingMiddleware", "PrometheusMiddleware"}.issubset(middleware_names)


@pytest.mark.asyncio()
async def test_get_session_yields_session(monkeypatch):
    fake_session = AsyncMock()

    class _Factory:
        async def __aenter__(self):
            return fake_session

        async def __aexit__(self, exc_type, exc, tb):
            pass

    async def _session_factory():
        return _Factory()

    monkeypatch.setattr(
        session_dep,
        "SessionFactory",
        MagicMock(return_value=_Factory()),
    )

    gen = session_dep.get_session()
    session = await gen.__anext__()
    assert session is fake_session
    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()


@pytest.mark.asyncio()
async def test_lifespan_starts_and_stops_producer(monkeypatch):
    fake_producer = AsyncMock()
    monkeypatch.setattr(
        kafka_dep.kafka_manager,
        "set_producer",
        lambda key, producer: None,
    )
    monkeypatch.setattr(
        kafka_dep.kafka_manager,
        "get_producer",
        lambda key: fake_producer,
    )

    async with server.lifespan(server.create_app()):
        fake_producer.start.assert_awaited_once()
    fake_producer.stop.assert_awaited_once()
