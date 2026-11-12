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
async def test_window_capacity_admits_count_calls():
    """`count` calls pass immediately; the next one reserves a future slot."""
    limiter = RateLimiter(windows=[Window(name="minute", count=2, interval_ms=60_000)])

    mock_sleep = AsyncMock()
    with (
        patch.object(time, "time", _time_stub([1_000.0, 1_020.0, 1_020.0])),
        patch.object(asyncio, "sleep", mock_sleep),
    ):
        # both slots of the window are free: no sleep, even though the
        # two calls are only 20s apart
        await limiter.check()
        mock_sleep.assert_not_called()

        await limiter.check()
        mock_sleep.assert_not_called()

        # third call: the window is full, the oldest reservation frees
        # at 1000 + 60 = 1060
        await limiter.check()
        mock_sleep.assert_awaited_once_with(40.0)


@pytest.mark.asyncio
async def test_sleeps_sub_second_intervals():
    limiter = RateLimiter(windows=[Window(name="fast", count=2, interval_ms=500)])

    mock_sleep = AsyncMock()
    with (
        patch.object(time, "time", _time_stub([1_000.0, 1_000.3, 1_000.3])),
        patch.object(asyncio, "sleep", mock_sleep),
    ):
        await limiter.check()
        mock_sleep.assert_not_called()

        await limiter.check()
        mock_sleep.assert_not_called()

        # third call waits for the first reservation to expire at 1000.5
        await limiter.check()
        mock_sleep.assert_awaited_once_with(0.2)


@pytest.mark.asyncio
async def test_reservations_slide_with_the_window():
    limiter = RateLimiter(windows=[Window(name="minute", count=2, interval_ms=10_000)])

    mock_sleep = AsyncMock()
    with (
        patch.object(time, "time", _time_stub([1_000.0, 1_005.0, 1_011.0, 1_011.0])),
        patch.object(asyncio, "sleep", mock_sleep),
    ):
        await limiter.check()
        await limiter.check()
        mock_sleep.assert_not_called()

        # the call at t=1000 slid out of the window (1000 + 10s = 1010
        # has passed): the slot is free again
        await limiter.check()
        mock_sleep.assert_not_called()

        # the next free slot is the second reservation + 10s = 1015
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
        await limiter.check()
        mock_sleep.assert_not_called()

        # both slots of the 1s window are taken: the third call waits
        # for the oldest reservation to expire at 1000 + 1s
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
        # exhaust both windows: the 1s window first (calls 3-5 queue
        # behind its reservations), then the 60s window binds
        for _ in range(6):
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
        # calls 1-2 fill both windows without waiting; call 3 queues
        # behind the second window's reservations, call 4 hits the
        # exhausted minute window
        for _ in range(4):
            await limiter.check()

    assert len(events) == 2

    first = events[0]
    assert [w.name for w in first.blocked] == ["second"]
    assert first.binding.name == "second"
    assert first.wait_s == 1.0

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


@pytest.mark.asyncio
async def test_concurrent_callers_never_overshoot_the_window():
    """The reservation guarantee under contention: at most `count`
    calls fire within any `interval` span, no matter how many callers
    hammer check() at once. The old check-in-time accounting leaked
    bursts past the window in this exact scenario."""
    limiter = RateLimiter(windows=[Window(name="burst", count=10, interval_ms=1_000)])
    fire_times: list[float] = []

    async def caller() -> None:
        await limiter.check()
        fire_times.append(time.perf_counter())

    await asyncio.gather(*[caller() for _ in range(40)])

    assert len(fire_times) == 40
    ordered = sorted(fire_times)
    # calls i and i+10 must be at least one window apart, or 11 calls
    # would have fired inside a single 1s window
    for i in range(len(ordered) - 10):
        assert ordered[i + 10] - ordered[i] >= 0.99


@pytest.mark.asyncio
async def test_concurrent_callers_wake_staggered():
    """Blocked callers reserve successive slots instead of all waking
    at once. The guarantee is the window bound, not perfect spacing:
    with count=2, callers may share a slot, but callers two apart must
    be a full interval apart (else 3 calls fired inside the window)."""
    limiter = RateLimiter(windows=[Window(name="burst", count=2, interval_ms=1_000)])

    # exhaust the window synchronously
    await limiter.check()
    await limiter.check()

    waits: list[float] = []

    async def caller() -> None:
        start = time.perf_counter()
        await limiter.check()
        waits.append(time.perf_counter() - start)

    await asyncio.gather(*[caller() for _ in range(4)])

    # two waiters may share a slot (the bound is count per interval,
    # not perfect spacing), so equal sleeps land in arbitrary order
    ordered = sorted(waits)
    assert ordered[2] - ordered[0] >= 0.95
    assert ordered[3] - ordered[1] >= 0.95
