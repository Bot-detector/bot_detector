from unittest.mock import AsyncMock

import aiohttp
import pytest
from aioresponses import aioresponses
from bot_detector.public_api.v2.core import PublicApiClient
from bot_detector.rate_limiter import RateLimiter


@pytest.fixture
def limiter():
    limiter = AsyncMock(spec=RateLimiter)
    limiter.check = AsyncMock()
    return limiter


@pytest.mark.asyncio
async def test_get_report_score_does_not_retry_on_404(limiter):
    url = "https://api.prd.osrsbotdetector.com/v2/player/report/score?name=test"

    with aioresponses() as mocked:
        mocked.get(url, status=404)
        mocked.get(url, status=404)
        mocked.get(url, status=404)

        async with aiohttp.ClientSession() as session:
            client = PublicApiClient(session=session, limiter=limiter)
            with pytest.raises(aiohttp.ClientResponseError):
                await client.get_report_score(names=["test"])

        assert limiter.check.call_count == 1, (
            f"Expected 1 call, got {limiter.check.call_count}. "
            "404 is a business error and should not be retried."
        )


@pytest.mark.asyncio
async def test_get_report_score_retries_on_connection_error(limiter):
    url = "https://api.prd.osrsbotdetector.com/v2/player/report/score?name=test"

    with aioresponses() as mocked:
        mocked.get(
            url,
            exception=aiohttp.ClientConnectionError("connection lost"),
        )
        mocked.get(
            url,
            status=200,
            payload=[
                {
                    "count": 1,
                    "possible_ban": False,
                    "confirmed_ban": False,
                    "confirmed_player": True,
                    "manual_detect": False,
                }
            ],
        )

        async with aiohttp.ClientSession() as session:
            client = PublicApiClient(session=session, limiter=limiter)
            result = await client.get_report_score(names=["test"])
            assert len(result) == 1

        assert limiter.check.call_count == 2
