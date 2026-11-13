"""Unit tests for HiscoreOldSchoolAPI: HTTP simulated, no sockets.

FakeSession mirrors the aiohttp client surface the brick touches
(get -> async CM -> response with status/history/json/raise_for_status),
so the brick's mapping logic is exercised without a transport. What a
fake cannot prove - real redirect following, real timeout timers, real
Jagex payload shape vs the validators - is the compose smoke's job:
make smoke-scraper runs this brick against the live API.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Optional, Union
from unittest.mock import AsyncMock

import aiohttp
import pytest
from aiohttp import ClientResponseError, ClientTimeout, RequestInfo
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

URL = "http://jagex.test/hiscore"


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


@dataclass(frozen=True)
class Hop:
    """One redirect hop as resp.history reports it."""

    status: int
    url: str = "http://jagex.test/first"


class FakeResponse:
    """The slice of aiohttp's ClientResponse the brick consumes."""

    def __init__(
        self,
        status: int = 200,
        payload: Optional[dict] = None,
        history: tuple[Hop, ...] = (),
        json_delay_s: float = 0.0,
    ) -> None:
        self.status = status
        self.payload = payload
        self.history = history
        self.url = URL
        self._json_delay_s = json_delay_s

    def raise_for_status(self) -> None:
        if self.status >= 400:
            request_info = RequestInfo(
                url=self.url, method="GET", headers={}, real_url=self.url
            )
            raise ClientResponseError(
                request_info, (), status=self.status, message="fake"
            )

    async def json(self) -> Optional[dict]:
        if self._json_delay_s:
            await asyncio.sleep(self._json_delay_s)
        return self.payload


Outcome = Union[FakeResponse, Exception]


class FakeSession:
    """Session double: each get() pops the next scripted outcome and
    records the kwargs the brick passed (timeout, proxy, params)."""

    def __init__(self, outcomes: list[Outcome]) -> None:
        self._outcomes = list(outcomes)
        self.calls: list[dict] = []

    @asynccontextmanager
    async def get(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        yield outcome


def _api(**kwargs) -> HiscoreOldSchoolAPI:
    return HiscoreOldSchoolAPI(url=URL, **kwargs)


def test_default_timeout_bounds_requests():
    # the component owns the time bound: aiohttp's 300s default must
    # never apply to a missing timeout argument
    api = HiscoreOldSchoolAPI()
    assert api.timeout == ClientTimeout(total=10, connect=5)


@pytest.mark.asyncio
async def test_get_success():
    session = FakeSession([FakeResponse(200, payload=_valid_hiscore_payload())])
    result = await _api().get("zezima", session)

    assert result.is_ok()
    assert isinstance(result, Ok)
    assert result.value.skills[0].name == "skill_0"
    assert result.latency > 0
    assert session.calls[0]["params"] == {"player": "zezima"}


@pytest.mark.asyncio
async def test_get_player_not_found():
    session = FakeSession([FakeResponse(404, payload={"error": "not found"})])
    result = await _api().get("nonexistent_player", session)

    assert result.is_err()
    assert isinstance(result, Err)
    assert isinstance(result.error, PlayerDoesNotExist)
    assert result.latency > 0


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
@pytest.mark.asyncio
async def test_get_unexpected_redirect(status: int):
    # the client follows the redirect; detection relies on resp.history
    session = FakeSession(
        [FakeResponse(200, payload={}, history=(Hop(status=status),))]
    )
    result = await _api().get("player", session)

    assert result.is_err()
    assert isinstance(result, Err)
    assert isinstance(result.error, UnexpectedRedirection)
    assert result.latency > 0


@pytest.mark.asyncio
async def test_get_server_error():
    session = FakeSession([FakeResponse(500, payload={"error": "boom"})])
    result = await _api().get("player", session)

    assert result.is_err()
    assert isinstance(result, Err)
    assert isinstance(result.error, ClientResponseError)
    assert result.error.status == 500
    assert result.latency > 0


@pytest.mark.asyncio
async def test_get_connection_error():
    # refused / dropped connections are transport outcomes
    session = FakeSession([aiohttp.ClientConnectionError("refused")])
    result = await _api().get("player", session)

    assert result.is_err()
    assert isinstance(result, Err)
    assert isinstance(result.error, aiohttp.ClientError)


@pytest.mark.asyncio
async def test_get_timeout_error():
    # a transport timeout surfaces as Err, not a raise
    session = FakeSession([asyncio.TimeoutError()])
    result = await _api().get("player", session)

    assert result.is_err()
    assert isinstance(result, Err)
    assert isinstance(result.error, (aiohttp.ClientError, asyncio.TimeoutError))
    assert result.latency > 0


@pytest.mark.asyncio
async def test_timeout_is_forwarded_to_session():
    timeout = ClientTimeout(total=3, connect=1)
    session = FakeSession([FakeResponse(200, payload=_valid_hiscore_payload())])
    await _api(timeout=timeout).get("player", session)

    assert session.calls[0]["timeout"] == timeout


@pytest.mark.asyncio
async def test_transform_invalid_data():
    session = FakeSession([FakeResponse(200, payload={"invalid": "structure"})])
    result = await _api().get("player", session)

    assert result.is_err()
    assert isinstance(result, Err)
    assert isinstance(result.error, ValidationError)


@pytest.mark.asyncio
async def test_transform_error_keeps_fetch_latency():
    # a ValidationError happens after the fetch: the Err must carry the
    # latency the fetch paid, or outcome metrics lose that scrape entirely
    session = FakeSession([FakeResponse(200, payload={"invalid": "structure"})])
    result = await _api().get("player", session)

    assert result.is_err()
    assert isinstance(result, Err)
    assert result.latency > 0


@pytest.mark.asyncio
async def test_truncated_payload_is_err():
    # a degraded response with only some skills must not scrape as success
    payload = _valid_hiscore_payload()
    payload["skills"] = payload["skills"][:1]
    session = FakeSession([FakeResponse(200, payload=payload)])
    result = await _api().get("player", session)

    assert result.is_err()
    assert isinstance(result, Err)
    assert isinstance(result.error, ValidationError)


@pytest.mark.asyncio
async def test_rate_limiter_is_called():
    mock_limiter = AsyncMock()
    session = FakeSession([FakeResponse(200, payload=_valid_hiscore_payload())])
    await _api(rate_limiter=mock_limiter).get("player", session)

    mock_limiter.check.assert_awaited_once()


@pytest.mark.asyncio
async def test_rate_limiter_failure_propagates():
    # the limiter is an injected scheduler: its errors are bugs and must
    # not be converted to Err values
    class ExplodingLimiter(RateLimiter):
        async def check(self) -> None:
            raise RuntimeError("limiter bug")

    session = FakeSession([FakeResponse(200, payload=_valid_hiscore_payload())])
    with pytest.raises(RuntimeError):
        await _api(rate_limiter=ExplodingLimiter(windows=[])).get("player", session)


@pytest.mark.asyncio
async def test_cancellation_propagates():
    # cancellation is BaseException: the fetch error handling must not
    # convert it to an Err value, mid-body-read or not
    session = FakeSession(
        [FakeResponse(200, payload=_valid_hiscore_payload(), json_delay_s=5.0)]
    )
    task = asyncio.create_task(_api().get("player", session))
    await asyncio.sleep(0.05)
    task.cancel()
    outcomes = await asyncio.gather(task, return_exceptions=True)

    assert isinstance(outcomes[0], asyncio.CancelledError)


@pytest.mark.asyncio
async def test_extra_skill_ids_logged_once(caplog):
    # tolerated, but must surface in the logs exactly once per distinct
    # set: a drifted payload scraped 1800 times must not spam the logs
    from bot_detector.osrs_hs_api import core

    core._REPORTED_DRIFT.clear()
    payload = _valid_hiscore_payload()
    payload["skills"].append(_skill(999))
    session = FakeSession(
        [FakeResponse(200, payload=payload), FakeResponse(200, payload=payload)]
    )
    with caplog.at_level(logging.WARNING, logger="bot_detector.osrs_hs_api.core"):
        await _api().get("player", session)
        await _api().get("player", session)

    drift = [r for r in caplog.records if "unexpected skill ids" in r.getMessage()]
    assert len(drift) == 1
    assert "[999]" in drift[0].getMessage()


@pytest.mark.asyncio
async def test_get_with_proxy_passes_to_session():
    proxy_url = "http://user:pass@proxy.example.com:8080"
    session = FakeSession([FakeResponse(200, payload=_valid_hiscore_payload())])
    await _api().get("zezima", session, proxy=proxy_url)

    assert session.calls[0]["proxy"] == proxy_url
