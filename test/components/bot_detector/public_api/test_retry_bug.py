"""Retry contract for PublicApiClient.get_report_score against a real server.

404 is a business error and must NOT be retried; connection errors must be
retried exactly once.
"""

from unittest.mock import AsyncMock

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from bot_detector.public_api.v2.core import PublicApiClient
from bot_detector.rate_limiter import RateLimiter

_SCORE_PAYLOAD = [
    {
        "count": 1,
        "possible_ban": False,
        "confirmed_ban": False,
        "confirmed_player": True,
        "manual_detect": False,
    }
]


def _build_app(plan: list) -> tuple[web.Application, dict]:
    """Executes `plan` entries in order: ("status", 404) or ("drop", None) or
    ("json", payload). Falls through to 200 + last json entry when exhausted.
    """
    state = {"call": 0}
    calls = {"n": 0}

    async def score(request: web.Request) -> web.Response:
        idx = min(state["call"], len(plan) - 1)
        state["call"] += 1
        calls["n"] += 1
        kind, value = plan[idx]
        if kind == "drop":
            # simulate a connection error: close without responding
            assert request.transport is not None
            request.transport.close()
            raise web.HTTPServiceUnavailable
        if kind == "status":
            return web.Response(status=value)
        return web.json_response(value)

    app = web.Application()
    app.router.add_get("/v2/player/report/score", score)
    return app, calls


async def _start(plan: list) -> tuple[TestServer, dict]:
    app, calls = _build_app(plan)
    server = TestServer(app)
    await server.start_server()
    return server, calls


@pytest.fixture
def limiter():
    limiter = AsyncMock(spec=RateLimiter)
    limiter.check = AsyncMock()
    return limiter


@pytest.mark.asyncio
async def test_get_report_score_does_not_retry_on_404(limiter):
    server, calls = await _start([("status", 404)])
    try:
        async with aiohttp.ClientSession() as session:
            client = PublicApiClient(
                session=session,
                limiter=limiter,
                base_url=str(server.make_url("")),
            )
            with pytest.raises(aiohttp.ClientResponseError):
                await client.get_report_score(names=["test"])
    finally:
        await server.close()

    assert calls["n"] == 1, (
        f"Expected exactly 1 request, server saw {calls['n']}. "
        "404 is a business error and should not be retried."
    )
    assert limiter.check.call_count == 1, (
        f"Expected 1 call, got {limiter.check.call_count}. "
        "404 is a business error and should not be retried."
    )


@pytest.mark.asyncio
async def test_get_report_score_retries_on_connection_error(limiter):
    server, calls = await _start([("drop", None), ("json", _SCORE_PAYLOAD)])
    try:
        async with aiohttp.ClientSession() as session:
            client = PublicApiClient(
                session=session,
                limiter=limiter,
                base_url=str(server.make_url("")),
            )
            result = await client.get_report_score(names=["test"])
            assert len(result) == 1
    finally:
        await server.close()

    # the dropped connection must be retried exactly once, whatever layer
    # performs it: aiohttp >= 3.12 retries idempotent GETs transparently at
    # the transport level (fed by reusable request bodies), so the @retry
    # decorator only fires for errors the transport cannot absorb
    # (e.g. ClientConnectorError)
    assert calls["n"] == 2, (
        f"Expected the request to be retried once (server saw {calls['n']})."
    )
    # transport-level retry bypasses the rate limiter by design
    assert limiter.check.call_count == 1
