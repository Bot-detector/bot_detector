"""Tests for HiscoreOldSchoolAPI against a real aiohttp test server.

Real redirect following is exercised on purpose: Jagex's edge serves the
hiscores "down" page as a 302 -> /community, and the API must detect it via
resp.history.
"""

from unittest.mock import AsyncMock, patch

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from bot_detector.osrs_hs_api.core import HiscoreOldSchoolAPI
from bot_detector.osrs_hs_api.exceptions import (
    PlayerDoesNotExist,
    UnexpectedRedirection,
)


def _valid_hiscore_payload():
    return {
        "skills": [
            {"id": 0, "name": "Attack", "rank": 1000, "level": 99, "xp": 13034431}
        ],
        "activities": [{"id": 0, "name": "Bounty Hunter", "rank": 500, "score": 100}],
    }


def _build_app(payload, status=200):
    async def hiscore(request: web.Request) -> web.Response:
        if status == 302:
            raise web.HTTPFound("/main")
        return web.json_response(payload, status=status)

    async def main(request: web.Request) -> web.Response:
        return web.json_response({})

    app = web.Application()
    app.router.add_get("/hiscore", hiscore)
    app.router.add_get("/main", main)
    return app


async def _start(payload, status=200) -> TestServer:
    server = TestServer(_build_app(payload, status))
    await server.start_server()
    return server


def _patch_url(monkeypatch: pytest.MonkeyPatch, server: TestServer):
    monkeypatch.setattr(HiscoreOldSchoolAPI, "url", str(server.make_url("/hiscore")))


@pytest.mark.asyncio
async def test_get_success(monkeypatch: pytest.MonkeyPatch):
    server = await _start(_valid_hiscore_payload())
    _patch_url(monkeypatch, server)
    api = HiscoreOldSchoolAPI()
    try:
        async with aiohttp.ClientSession() as session:
            result = await api.get("zezima", session)
    finally:
        await server.close()

    assert result.is_ok()
    assert result.value.skills[0].name == "Attack"
    assert result.latency > 0


@pytest.mark.asyncio
async def test_get_player_not_found(monkeypatch: pytest.MonkeyPatch):
    server = await _start({"error": "not found"}, status=404)
    _patch_url(monkeypatch, server)
    api = HiscoreOldSchoolAPI()
    try:
        async with aiohttp.ClientSession() as session:
            result = await api.get("nonexistent_player", session)
    finally:
        await server.close()

    assert result.is_err()
    assert isinstance(result.error, PlayerDoesNotExist)


@pytest.mark.asyncio
async def test_get_unexpected_redirect(monkeypatch: pytest.MonkeyPatch):
    # 302 -> /main is followed by the client; detection relies on resp.history
    server = await _start({}, status=302)
    _patch_url(monkeypatch, server)
    api = HiscoreOldSchoolAPI()
    try:
        async with aiohttp.ClientSession() as session:
            result = await api.get("player", session)
    finally:
        await server.close()

    assert result.is_err()
    assert isinstance(result.error, UnexpectedRedirection)


@pytest.mark.asyncio
async def test_get_server_error(monkeypatch: pytest.MonkeyPatch):
    server = await _start({"error": "boom"}, status=500)
    _patch_url(monkeypatch, server)
    api = HiscoreOldSchoolAPI()
    try:
        async with aiohttp.ClientSession() as session:
            result = await api.get("player", session)
    finally:
        await server.close()

    assert result.is_err()
    assert isinstance(result.error, Exception)


@pytest.mark.asyncio
async def test_get_connection_error(monkeypatch: pytest.MonkeyPatch):
    # port 1 on localhost is closed: connect must fail with a client error.
    # Depending on the OS this surfaces as ClientConnectorError (refused) or
    # ConnectionTimeoutError (filtered/dropped); both are aiohttp ClientErrors.
    api = HiscoreOldSchoolAPI()
    monkeypatch.setattr(HiscoreOldSchoolAPI, "url", "http://127.0.0.1:1/hiscore")
    async with aiohttp.ClientSession() as session:
        result = await api.get("player", session)

    assert result.is_err()
    assert isinstance(result.error, aiohttp.ClientError)


@pytest.mark.asyncio
async def test_transform_invalid_data(monkeypatch: pytest.MonkeyPatch):
    from pydantic import ValidationError

    server = await _start({"invalid": "structure"})
    _patch_url(monkeypatch, server)
    api = HiscoreOldSchoolAPI()
    try:
        async with aiohttp.ClientSession() as session:
            result = await api.get("player", session)
    finally:
        await server.close()

    assert result.is_err()
    assert isinstance(result.error, ValidationError)


@pytest.mark.asyncio
async def test_rate_limiter_is_called(monkeypatch: pytest.MonkeyPatch):
    server = await _start(_valid_hiscore_payload())
    _patch_url(monkeypatch, server)
    mock_limiter = AsyncMock()
    api = HiscoreOldSchoolAPI(rate_limiter=mock_limiter)
    try:
        async with aiohttp.ClientSession() as session:
            await api.get("player", session)
    finally:
        await server.close()

    mock_limiter.check.assert_awaited_once()


@pytest.mark.asyncio
async def test_latency_is_recorded(monkeypatch: pytest.MonkeyPatch):
    server = await _start(_valid_hiscore_payload())
    _patch_url(monkeypatch, server)
    api = HiscoreOldSchoolAPI()
    try:
        async with aiohttp.ClientSession() as session:
            result = await api.get("zezima", session)
    finally:
        await server.close()

    assert result.is_ok()
    assert isinstance(result.latency, float)
    assert result.latency >= 0


@pytest.mark.asyncio
async def test_get_with_proxy_passes_to_session(
    monkeypatch: pytest.MonkeyPatch,
):
    server = await _start(_valid_hiscore_payload())
    _patch_url(monkeypatch, server)
    api = HiscoreOldSchoolAPI()
    proxy_url = "http://user:pass@proxy.example.com:8080"
    try:
        async with aiohttp.ClientSession() as session:
            with patch.object(session, "get", wraps=session.get) as mock_get:
                result = await api.get("zezima", session, proxy=proxy_url)
                mock_get.assert_called_once()
                call_kwargs = mock_get.call_args[1]
                assert call_kwargs.get("proxy") == proxy_url
    finally:
        await server.close()

    # example.com proxy cannot reach the local test server; the kwarg assert
    # above is the contract under test
    assert result.is_err() or result.is_ok()


@pytest.mark.asyncio
async def test_get_with_dead_proxy_returns_err():
    # a proxy that refuses connections surfaces as an Err result
    api = HiscoreOldSchoolAPI()
    dead_proxy = "http://user:pass@127.0.0.1:1"
    async with aiohttp.ClientSession() as session:
        result = await api.get("player", session, proxy=dead_proxy)

    assert result.is_err()
    assert isinstance(result.error, aiohttp.ClientError)
