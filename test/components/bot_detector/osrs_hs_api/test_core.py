"""Tests for HiscoreOldSchoolAPI against a real aiohttp test server.

Real redirect following is exercised on purpose: Jagex's edge serves the
hiscores "down" page as a redirect to /community, and the API must detect
it via resp.history.
"""

import asyncio
import socket
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest
from aiohttp import ClientResponseError, ClientTimeout, web
from aiohttp.test_utils import TestServer
from bot_detector.osrs_hs_api.core import HiscoreOldSchoolAPI
from bot_detector.osrs_hs_api.exceptions import (
    Err,
    Ok,
    PlayerDoesNotExist,
    UnexpectedRedirection,
)
from bot_detector.osrs_hs_api.structs import EXPECTED_SKILL_IDS
from bot_detector.rate_limiter import RateLimiter
from pydantic import ValidationError


def closed_port() -> int:
    """An ephemeral port with no listener: connect is refused at once.

    Hard-coding a privileged port hangs behind firewalls that DROP
    instead of REJECT (30s+ connect timeout); a fresh bind-then-close
    socket fails with a connection-level ClientError everywhere.
    """
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _skill(i: int) -> dict:
    return {"id": i, "name": f"skill_{i}", "rank": 100, "level": 50, "xp": 1000}


def _valid_hiscore_payload() -> dict:
    return {
        "skills": [_skill(i) for i in sorted(EXPECTED_SKILL_IDS)],
        "activities": [
            {"id": 0, "name": "Bounty Hunter", "rank": 500, "score": 100},
            {"id": 3, "name": "Clue Scrolls", "rank": 42, "score": 7},
        ],
    }


def _build_app(
    payload: dict, status: int = 200, delay_s: float = 0.0
) -> web.Application:
    async def hiscore(request: web.Request) -> web.StreamResponse:
        if delay_s:
            await asyncio.sleep(delay_s)
        if status in (301, 302, 303, 307, 308):
            return web.Response(status=status, headers={"Location": "/main"})
        return web.json_response(payload, status=status)

    async def main(request: web.Request) -> web.Response:
        return web.json_response({})

    app = web.Application()
    app.router.add_get("/hiscore", hiscore)
    app.router.add_get("/main", main)
    return app


async def _start(payload: dict, status: int = 200, delay_s: float = 0.0) -> TestServer:
    server = TestServer(_build_app(payload, status, delay_s))
    await server.start_server()
    return server


def _api(server: TestServer, **kwargs) -> HiscoreOldSchoolAPI:
    return HiscoreOldSchoolAPI(url=str(server.make_url("/hiscore")), **kwargs)


def test_default_timeout_bounds_requests():
    # the component owns the time bound: aiohttp's 300s default must
    # never apply to a missing timeout argument
    api = HiscoreOldSchoolAPI()
    assert api.timeout == ClientTimeout(total=10, connect=5)


@pytest.mark.asyncio
async def test_get_success():
    server = await _start(_valid_hiscore_payload())
    api = _api(server)
    try:
        async with aiohttp.ClientSession() as session:
            result = await api.get("zezima", session)
    finally:
        await server.close()

    assert result.is_ok()
    assert isinstance(result, Ok)
    assert result.value.skills[0].name == "skill_0"
    assert result.latency > 0


@pytest.mark.asyncio
async def test_get_player_not_found():
    server = await _start({"error": "not found"}, status=404)
    api = _api(server)
    try:
        async with aiohttp.ClientSession() as session:
            result = await api.get("nonexistent_player", session)
    finally:
        await server.close()

    assert result.is_err()
    assert isinstance(result, Err)
    assert isinstance(result.error, PlayerDoesNotExist)
    assert result.latency > 0


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
@pytest.mark.asyncio
async def test_get_unexpected_redirect(status: int):
    # the client follows the redirect; detection relies on resp.history
    server = await _start({}, status=status)
    api = _api(server)
    try:
        async with aiohttp.ClientSession() as session:
            result = await api.get("player", session)
    finally:
        await server.close()

    assert result.is_err()
    assert isinstance(result, Err)
    assert isinstance(result.error, UnexpectedRedirection)
    assert result.latency > 0


@pytest.mark.asyncio
async def test_get_server_error():
    server = await _start({"error": "boom"}, status=500)
    api = _api(server)
    try:
        async with aiohttp.ClientSession() as session:
            result = await api.get("player", session)
    finally:
        await server.close()

    assert result.is_err()
    assert isinstance(result, Err)
    assert isinstance(result.error, ClientResponseError)
    assert result.error.status == 500
    assert result.latency > 0


@pytest.mark.asyncio
async def test_get_connection_error():
    # a port with no listener: connect must fail with a client error.
    # Depending on the OS this surfaces as ClientConnectorError (refused) or
    # ConnectionTimeoutError (filtered/dropped); both are aiohttp ClientErrors.
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    api = HiscoreOldSchoolAPI(url=f"http://127.0.0.1:{port}/hiscore")
    async with aiohttp.ClientSession() as session:
        result = await api.get("player", session)

    assert result.is_err()
    assert isinstance(result, Err)
    assert isinstance(result.error, aiohttp.ClientError)


@pytest.mark.asyncio
async def test_transform_invalid_data():
    server = await _start({"invalid": "structure"})
    api = _api(server)
    try:
        async with aiohttp.ClientSession() as session:
            result = await api.get("player", session)
    finally:
        await server.close()

    assert result.is_err()
    assert isinstance(result, Err)
    assert isinstance(result.error, ValidationError)


@pytest.mark.asyncio
async def test_transform_error_keeps_fetch_latency():
    # a ValidationError happens after the fetch: the Err must carry the
    # latency the fetch paid, or outcome metrics lose that scrape entirely
    server = await _start({"invalid": "structure"})
    api = _api(server)
    try:
        async with aiohttp.ClientSession() as session:
            result = await api.get("player", session)
    finally:
        await server.close()

    assert result.is_err()
    assert isinstance(result, Err)
    assert result.latency > 0


@pytest.mark.asyncio
async def test_truncated_payload_is_err():
    # a degraded response with only some skills must not scrape as success
    payload = _valid_hiscore_payload()
    payload["skills"] = payload["skills"][:1]
    server = await _start(payload)
    api = _api(server)
    try:
        async with aiohttp.ClientSession() as session:
            result = await api.get("player", session)
    finally:
        await server.close()

    assert result.is_err()
    assert isinstance(result, Err)
    assert isinstance(result.error, ValidationError)


@pytest.mark.asyncio
async def test_rate_limiter_is_called():
    server = await _start(_valid_hiscore_payload())
    mock_limiter = AsyncMock()
    api = _api(server, rate_limiter=mock_limiter)
    try:
        async with aiohttp.ClientSession() as session:
            await api.get("player", session)
    finally:
        await server.close()

    mock_limiter.check.assert_awaited_once()


@pytest.mark.asyncio
async def test_rate_limiter_failure_propagates():
    # the limiter is an injected scheduler: its errors are bugs and must
    # not be converted to Err values
    class ExplodingLimiter(RateLimiter):
        async def check(self) -> None:
            raise RuntimeError("limiter bug")

    server = await _start(_valid_hiscore_payload())
    api = _api(server, rate_limiter=ExplodingLimiter(windows=[]))
    try:
        async with aiohttp.ClientSession() as session:
            with pytest.raises(RuntimeError):
                await api.get("player", session)
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_timeout_bounds_slow_response():
    # the request must fail at the configured timeout, not aiohttp's 300s default
    server = await _start(_valid_hiscore_payload(), delay_s=1.0)
    api = _api(server, timeout=ClientTimeout(total=0.2))
    try:
        async with aiohttp.ClientSession() as session:
            result = await api.get("player", session)
    finally:
        await server.close()

    assert result.is_err()
    assert isinstance(result, Err)
    assert isinstance(result.error, (aiohttp.ClientError, asyncio.TimeoutError))
    assert result.latency < 0.9


@pytest.mark.asyncio
async def test_cancellation_propagates():
    # cancellation is BaseException: the broad fetch error handling must
    # not convert it to an Err value
    server = await _start(_valid_hiscore_payload(), delay_s=1.0)
    api = _api(server)
    try:
        async with aiohttp.ClientSession() as session:
            task = asyncio.create_task(api.get("player", session))
            await asyncio.sleep(0.05)
            task.cancel()
            outcomes = await asyncio.gather(task, return_exceptions=True)
    finally:
        await server.close()

    assert isinstance(outcomes[0], asyncio.CancelledError)


@pytest.mark.asyncio
async def test_latency_is_recorded():
    server = await _start(_valid_hiscore_payload())
    api = _api(server)
    try:
        async with aiohttp.ClientSession() as session:
            result = await api.get("zezima", session)
    finally:
        await server.close()

    assert result.is_ok()
    assert isinstance(result.latency, float)
    assert result.latency >= 0


@pytest.mark.asyncio
async def test_get_with_proxy_passes_to_session():
    server = await _start(_valid_hiscore_payload())
    api = _api(server)
    proxy_url = "http://user:pass@proxy.example.com:8080"
    try:
        async with aiohttp.ClientSession() as session:
            with patch.object(session, "get", wraps=session.get) as mock_get:
                await api.get("zezima", session, proxy=proxy_url)
                mock_get.assert_called_once()
                call_kwargs = mock_get.call_args[1]
                assert call_kwargs.get("proxy") == proxy_url
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_get_with_dead_proxy_returns_err():
    # a proxy that refuses connections surfaces as an Err result
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    dead_proxy = f"http://user:pass@127.0.0.1:{port}"
    api = HiscoreOldSchoolAPI()
    async with aiohttp.ClientSession() as session:
        result = await api.get("player", session, proxy=dead_proxy)

    assert result.is_err()
    assert isinstance(result, Err)
    assert isinstance(result.error, aiohttp.ClientError)
