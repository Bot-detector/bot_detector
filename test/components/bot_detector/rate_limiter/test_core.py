import asyncio
import time
from collections.abc import Callable
from unittest.mock import AsyncMock, patch

import pytest
from bot_detector.rate_limiter import RateLimiter, WaitEvent, Window


def _time_stub(schedule: list[float]) -> Callable[[], float]:
    """time.time stub serving scheduled values, then repeating the last.

    Extra reads (e.g. logging's LogRecord timestamp when the root logger
    is at INFO, which logfmt enables process-wide) must not exhaust the
    schedule, or check() crashes with StopIteration.
    """
    remaining = iter(schedule)
    current = schedule[0]

    def fake() -> float:
        nonlocal current
        try:
            current = next(remaining)
        except StopIteration:
            pass
        return current

    return fake


@pytest.mark.asyncio
async def test_windows_are_kept_in_order():
    windows = [
        Window(name="minute", count=1200, interval_ms=60_000),
        Window(name="second", count=20, interval_ms=1_000),
    ]
    limiter = RateLimiter(windows=windows)

    assert limiter.windows == tuple(windows)


@pytest.mark.asyncio
async def test_no_sleep_before_limit():
    limiter = RateLimiter(windows=[Window(name="minute", count=5, interval_ms=60_000)])

    mock_sleep = AsyncMock()
    with (
        patch.object(time, "time", return_value=1_000.0),
        patch.object(asyncio, "sleep", mock_sleep),
    ):
        for _ in range(4):
            await limiter.check()

    mock_sleep.assert_not_called()


@pytest.mark.asyncio
async def test_sleep_when_full_and_within_interval():
    limiter = RateLimiter(windows=[Window(name="minute", count=3, interval_ms=60_000)])

    mock_sleep = AsyncMock()
    with (
        patch.object(time, "time", return_value=1_000.0),
        patch.object(asyncio, "sleep", mock_sleep),
    ):
        await limiter.check()
        await limiter.check()
        mock_sleep.assert_not_called()

        await limiter.check()
        mock_sleep.assert_awaited_once_with(60.0)


@pytest.mark.asyncio
async def test_no_sleep_when_full_but_outside_interval():
    limiter = RateLimiter(windows=[Window(name="minute", count=3, interval_ms=10_000)])

    mock_sleep = AsyncMock()
    with (
        patch.object(time, "time", _time_stub([1_000.0, 1_003.0, 1_011.0])),
        patch.object(asyncio, "sleep", mock_sleep),
    ):
        await limiter.check()
        await limiter.check()
        mock_sleep.assert_not_called()

        await limiter.check()
        mock_sleep.assert_not_called()


@pytest.mark.asyncio
async def test_sleep_duration_calculation():
    limiter = RateLimiter(windows=[Window(name="minute", count=2, interval_ms=60_000)])

    mock_sleep = AsyncMock()
    with (
        patch.object(time, "time", _time_stub([1_000.0, 1_020.0])),
        patch.object(asyncio, "sleep", mock_sleep),
    ):
        await limiter.check()
        mock_sleep.assert_not_called()

        await limiter.check()
        mock_sleep.assert_awaited_once_with(40.0)


@pytest.mark.asyncio
async def test_sleeps_sub_second_intervals():
    limiter = RateLimiter(windows=[Window(name="fast", count=2, interval_ms=500)])

    mock_sleep = AsyncMock()
    with (
        patch.object(time, "time", _time_stub([1_000.0, 1_000.3])),
        patch.object(asyncio, "sleep", mock_sleep),
    ):
        await limiter.check()
        mock_sleep.assert_not_called()

        await limiter.check()
        mock_sleep.assert_awaited_once_with(0.2)


@pytest.mark.asyncio
async def test_history_is_sliding():
    limiter = RateLimiter(windows=[Window(name="minute", count=2, interval_ms=10_000)])

    mock_sleep = AsyncMock()
    with (
        patch.object(time, "time", _time_stub([1_000.0, 1_005.0, 1_011.0])),
        patch.object(asyncio, "sleep", mock_sleep),
    ):
        await limiter.check()
        await limiter.check()
        mock_sleep.assert_awaited_once_with(5.0)

        # the call at t=1000 slid out of the window: spans 6s
        await limiter.check()
        mock_sleep.assert_awaited_with(4.0)


@pytest.mark.asyncio
async def test_multiple_windows_cap_shortest_interval():
    limiter = RateLimiter(
        windows=[
            Window(name="minute", count=1200, interval_ms=60_000),
            Window(name="second", count=2, interval_ms=1_000),
        ]
    )

    mock_sleep = AsyncMock()
    with (
        patch.object(time, "time", return_value=1_000.0),
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
            Window(name="minute", count=2, interval_ms=60_000),
            Window(name="second", count=2, interval_ms=1_000),
        ]
    )

    mock_sleep = AsyncMock()
    with (
        patch.object(time, "time", _time_stub([1_000.0, 1_061.0, 1_122.0])),
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
            Window(name="minute", count=5, interval_ms=60_000),
            Window(name="second", count=2, interval_ms=1_000),
        ]
    )

    mock_sleep = AsyncMock()
    with (
        patch.object(time, "time", return_value=1_000.0),
        patch.object(asyncio, "sleep", mock_sleep),
    ):
        # exhaust both windows: the 1s window first, then the 60s window
        for _ in range(5):
            await limiter.check()

    mock_sleep.assert_any_call(1.0)
    mock_sleep.assert_awaited_with(60.0)


@pytest.mark.asyncio
async def test_on_wait_reports_blocked_and_binding():
    limiter = RateLimiter(
        windows=[
            Window(name="minute", count=3, interval_ms=60_000),
            Window(name="second", count=2, interval_ms=1_000),
        ],
    )
    events: list[WaitEvent] = []
    limiter.on_wait = events.append

    with (
        patch.object(time, "time", return_value=1_000.0),
        patch.object(asyncio, "sleep", AsyncMock()),
    ):
        # call 2 exhausts the second window, call 3 exhausts both
        for _ in range(3):
            await limiter.check()

    assert len(events) == 2

    second_only = events[0]
    assert [w.name for w in second_only.blocked] == ["second"]
    assert second_only.binding.name == "second"
    assert second_only.wait_s == 1.0

    both = events[1]
    assert [w.name for w in both.blocked] == ["minute", "second"]
    # the minute window demands the longest wait, so it binds
    assert both.binding.name == "minute"
    assert both.wait_s == 60.0


@pytest.mark.asyncio
async def test_no_wait_event_when_unlimited():
    limiter = RateLimiter(windows=[Window(name="minute", count=5, interval_ms=60_000)])
    events: list[WaitEvent] = []
    limiter.on_wait = events.append

    with (
        patch.object(time, "time", return_value=1_000.0),
        patch.object(asyncio, "sleep", AsyncMock()),
    ):
        for _ in range(4):
            await limiter.check()

    assert events == []
