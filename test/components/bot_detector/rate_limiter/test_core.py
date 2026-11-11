import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest
from bot_detector.rate_limiter import RateLimiter, Window


@pytest.mark.asyncio
async def test_default_config():
    limiter = RateLimiter()

    assert limiter.windows == (Window(count=60, interval_ms=60_000),)


@pytest.mark.asyncio
async def test_no_sleep_before_limit():
    limiter = RateLimiter(windows=[Window(count=5, interval_ms=60_000)])

    mock_sleep = AsyncMock()
    with (
        patch.object(time, "time", return_value=1000),
        patch.object(asyncio, "sleep", mock_sleep),
    ):
        for _ in range(4):
            await limiter.check()

    mock_sleep.assert_not_called()


@pytest.mark.asyncio
async def test_sleep_when_full_and_within_interval():
    limiter = RateLimiter(windows=[Window(count=3, interval_ms=60_000)])

    mock_sleep = AsyncMock()
    with (
        patch.object(time, "time", return_value=1_000_000),
        patch.object(asyncio, "sleep", mock_sleep),
    ):
        await limiter.check()
        await limiter.check()
        mock_sleep.assert_not_called()

        await limiter.check()
        mock_sleep.assert_awaited_once_with(60.0)


@pytest.mark.asyncio
async def test_no_sleep_when_full_but_outside_interval():
    limiter = RateLimiter(windows=[Window(count=3, interval_ms=10_000)])

    mock_sleep = AsyncMock()
    time_values = [1_000_000, 1_003_000, 1_011_000]
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
async def test_sleep_duration_calculation():
    limiter = RateLimiter(windows=[Window(count=2, interval_ms=60_000)])

    mock_sleep = AsyncMock()
    time_values = [1_000_000, 1_020_000]
    time_iter = iter(time_values)

    with (
        patch.object(time, "time", side_effect=lambda: next(time_iter)),
        patch.object(asyncio, "sleep", mock_sleep),
    ):
        await limiter.check()
        mock_sleep.assert_not_called()

        await limiter.check()
        mock_sleep.assert_awaited_once_with(40.0)


@pytest.mark.asyncio
async def test_sleeps_sub_second_intervals():
    limiter = RateLimiter(windows=[Window(count=2, interval_ms=500)])

    mock_sleep = AsyncMock()
    time_values = [1_000_000, 1_000_300]
    time_iter = iter(time_values)

    with (
        patch.object(time, "time", side_effect=lambda: next(time_iter)),
        patch.object(asyncio, "sleep", mock_sleep),
    ):
        await limiter.check()
        mock_sleep.assert_not_called()

        await limiter.check()
        mock_sleep.assert_awaited_once_with(0.2)


@pytest.mark.asyncio
async def test_history_is_sliding():
    limiter = RateLimiter(windows=[Window(count=2, interval_ms=10_000)])

    mock_sleep = AsyncMock()
    time_values = [1_000_000, 1_005_000, 1_011_000]
    time_iter = iter(time_values)

    with (
        patch.object(time, "time", side_effect=lambda: next(time_iter)),
        patch.object(asyncio, "sleep", mock_sleep),
    ):
        await limiter.check()
        await limiter.check()
        mock_sleep.assert_awaited_once_with(5.0)

        # the call at t=1_000_000 slid out of the window: spans 6s
        await limiter.check()
        mock_sleep.assert_awaited_with(4.0)


@pytest.mark.asyncio
async def test_multiple_windows_cap_shortest_interval():
    limiter = RateLimiter(
        windows=[
            Window(count=1200, interval_ms=60_000),
            Window(count=2, interval_ms=1_000),
        ]
    )

    mock_sleep = AsyncMock()
    with (
        patch.object(time, "time", return_value=1_000_000),
        patch.object(asyncio, "sleep", mock_sleep),
    ):
        await limiter.check()
        mock_sleep.assert_not_called()

        # second call is allowed, third is capped by the 1s window
        await limiter.check()
        mock_sleep.assert_awaited_once_with(1.0)


@pytest.mark.asyncio
async def test_multiple_windows_allow_spread_calls():
    limiter = RateLimiter(
        windows=[
            Window(count=2, interval_ms=60_000),
            Window(count=2, interval_ms=1_000),
        ]
    )

    mock_sleep = AsyncMock()
    time_values = [1_000_000, 1_061_000, 1_122_000]
    time_iter = iter(time_values)

    with (
        patch.object(time, "time", side_effect=lambda: next(time_iter)),
        patch.object(asyncio, "sleep", mock_sleep),
    ):
        await limiter.check()
        await limiter.check()
        await limiter.check()

    # calls spaced beyond both intervals pass without sleeping
    mock_sleep.assert_not_called()


@pytest.mark.asyncio
async def test_sleeps_for_longest_window():
    limiter = RateLimiter(
        windows=[
            Window(count=5, interval_ms=60_000),
            Window(count=2, interval_ms=1_000),
        ]
    )

    mock_sleep = AsyncMock()
    with (
        patch.object(time, "time", return_value=1_000_000),
        patch.object(asyncio, "sleep", mock_sleep),
    ):
        # exhaust both windows: the 1s window first, then the 60s window
        for _ in range(5):
            await limiter.check()

    mock_sleep.assert_any_call(1.0)
    mock_sleep.assert_awaited_with(60.0)
