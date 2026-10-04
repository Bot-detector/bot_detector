"""Tests for RuneMetrics.get against a real aiohttp test server.

Real redirect following is exercised on purpose: when the hiscores are down,
Jagex redirects to the main page and the API must raise UnexpectedRedirection
based on resp.history.
"""

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from bot_detector.runemetrics_api import RuneMetrics
from bot_detector.runemetrics_api.exceptions import UnexpectedRedirection


def _player_payload():
    return {
        "name": "zezima",
        "rank": "1,000",
        "totalskill": 500,
        "totalxp": 100_000_000,
        "combatlevel": 126,
        "magic": 1,
        "melee": 2,
        "ranged": 3,
        "questsstarted": 4,
        "questscomplete": 5,
        "questsnotstarted": 6,
        "activities": [],
        "skillvalues": [],
        "loggedIn": False,
    }


def _build_app(payload, status=200):
    async def profile(request: web.Request) -> web.Response:
        if status == 302:
            raise web.HTTPFound("/main")
        return web.json_response(payload, status=status)

    async def main(request: web.Request) -> web.Response:
        return web.json_response({})

    app = web.Application()
    app.router.add_get("/profile", profile)
    app.router.add_get("/main", main)
    return app


async def _start(payload, status=200) -> TestServer:
    server = TestServer(_build_app(payload, status))
    await server.start_server()
    return server


def _patch_url(monkeypatch: pytest.MonkeyPatch, server: TestServer):
    monkeypatch.setattr(RuneMetrics, "BASE_URL", str(server.make_url("/profile")))


@pytest.mark.asyncio
async def test_get_success(monkeypatch: pytest.MonkeyPatch):
    server = await _start(_player_payload())
    _patch_url(monkeypatch, server)
    api = RuneMetrics()
    try:
        async with aiohttp.ClientSession() as session:
            data = await api.get("zezima", session)
    finally:
        await server.close()

    assert data.player is not None
    assert data.player.name == "zezima"
    assert data.error is None


@pytest.mark.asyncio
async def test_get_error_field(monkeypatch: pytest.MonkeyPatch):
    server = await _start({"error": "NO_PROFILE", "loggedIn": False})
    _patch_url(monkeypatch, server)
    api = RuneMetrics()
    try:
        async with aiohttp.ClientSession() as session:
            data = await api.get("nonexistent", session)
    finally:
        await server.close()

    assert data.player is None
    assert data.error is not None
    assert data.error.error == "NO_PROFILE"


@pytest.mark.asyncio
async def test_get_unexpected_redirect(monkeypatch: pytest.MonkeyPatch):
    # hiscores down: 302 to the main page, followed by the client, then a 200.
    # Detection must rely on resp.history (production contract).
    server = await _start({}, status=302)
    _patch_url(monkeypatch, server)
    api = RuneMetrics()
    try:
        async with aiohttp.ClientSession() as session:
            with pytest.raises(UnexpectedRedirection):
                await api.get("player", session)
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_get_non_200_raises(monkeypatch: pytest.MonkeyPatch):
    server = await _start({"error": "boom"}, status=500)
    _patch_url(monkeypatch, server)
    api = RuneMetrics()
    try:
        async with aiohttp.ClientSession() as session:
            with pytest.raises(aiohttp.ClientResponseError):
                await api.get("player", session)
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_get_return_latency(monkeypatch: pytest.MonkeyPatch):
    server = await _start(_player_payload())
    _patch_url(monkeypatch, server)
    api = RuneMetrics()
    try:
        async with aiohttp.ClientSession() as session:
            data, latency = await api.get("zezima", session, return_latency=True)
    finally:
        await server.close()

    assert data.player is not None
    assert latency > 0
