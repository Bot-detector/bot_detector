import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest
from bot_detector.rate_limiter import RateLimiter


@pytest.mark.asyncio
async def test_no_sleep_before_limit():
    limiter = RateLimiter(calls_per_interval=5, interval=60)

    with (
        patch.object(time, "time", return_value=1000),
        patch.object(asyncio, "sleep", AsyncMock()),
    ):
        for _ in range(4):
            await limiter.check()

    assert len(limiter.history) == 4


@pytest.mark.asyncio
async def test_sleep_when_full_and_within_interval():
    limiter = RateLimiter(calls_per_interval=3, interval=60)

    mock_sleep = AsyncMock()
    with (
        patch.object(time, "time", return_value=1000),
        patch.object(asyncio, "sleep", mock_sleep),
    ):
        await limiter.check()
        await limiter.check()
        mock_sleep.assert_not_called()

        await limiter.check()
        mock_sleep.assert_awaited_once_with(60)


@pytest.mark.asyncio
async def test_no_sleep_when_full_but_outside_interval():
    limiter = RateLimiter(calls_per_interval=3, interval=10)

    mock_sleep = AsyncMock()
    time_values = [1000, 1003, 1011]
    time_iter = iter(time_values)

    with (
        patch.object(time, "time", side_effect=lambda: next(time_iter)),
        patch.object(asyncio, "sleep", mock_sleep),
    ):
        await limiter.check()
        await limiter.check()
        mock_sleep.assert_not_called()

        await limiter.check()
        mock_sleep.assert_not_called()


@pytest.mark.asyncio
async def test_custom_config():
    limiter = RateLimiter(calls_per_interval=10, interval=30)

    assert limiter.history.maxlen == 10
    assert limiter.interval == 30


@pytest.mark.asyncio
async def test_sleep_duration_calculation():
    limiter = RateLimiter(calls_per_interval=2, interval=60)

    mock_sleep = AsyncMock()
    time_values = [1000, 1020]
    time_iter = iter(time_values)

    with (
        patch.object(time, "time", side_effect=lambda: next(time_iter)),
        patch.object(asyncio, "sleep", mock_sleep),
    ):
        await limiter.check()
        mock_sleep.assert_not_called()

        await limiter.check()
        mock_sleep.assert_awaited_once_with(40)


@pytest.mark.asyncio
async def test_default_config():
    limiter = RateLimiter()

    assert limiter.history.maxlen == 60
    assert limiter.interval == 60


@pytest.mark.asyncio
async def test_history_is_sliding():
    limiter = RateLimiter(calls_per_interval=3, interval=60)

    time_values = [1000, 1001, 1002]
    time_iter = iter(time_values)

    with (
        patch.object(time, "time", side_effect=lambda: next(time_iter)),
        patch.object(asyncio, "sleep", AsyncMock()),
    ):
        await limiter.check()
        await limiter.check()
        await limiter.check()

    assert len(limiter.history) == 3
    assert list(limiter.history) == [1000, 1001, 1002]
