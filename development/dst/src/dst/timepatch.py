"""Patch the sync ``time`` module onto a VirtualClock.

Layer for synchronous code with hardcoded ``time.time()`` /
``time.sleep()`` calls: inside the ``virtual_time`` context, reading
time returns the clock's virtual time and sleeping advances it, so
legacy blocking code runs instantly on the simulated timeline.

Scope notes:
- patches are process-wide (the ``time`` module is global); use one
  patch block at a time and never from multiple threads.
- ``datetime.now()`` reads ``time.time`` internally per platform, but
  DST does not promise it: patch ``datetime`` at the call site if a
  dependency needs wall-calendar dates (YAGNI until one does).
"""

import asyncio
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from .clock import VirtualClock
from .loop import VirtualEventLoop

_PATCHED_NAMES = (
    "time",
    "monotonic",
    "perf_counter",
    "sleep",
    "time_ns",
    "monotonic_ns",
    "perf_counter_ns",
)

_active: VirtualClock | None = None


@contextmanager
def virtual_time(clock: VirtualClock | None = None) -> Iterator[VirtualClock]:
    """Point the sync ``time`` module at ``clock`` inside the block.

    - ``time.time()`` / ``monotonic()`` / ``perf_counter()`` (and the
      ``*_ns`` variants) return virtual time.
    - ``time.sleep(s)`` advances the clock by ``s`` and returns
      immediately instead of blocking.

    Without ``clock``, the clock of the running VirtualEventLoop is
    used, so scenarios can patch their own timeline: inside
    ``dst.run``, ``with virtual_time():`` just works.

    Raises RuntimeError on nesting; restore is guaranteed on exit.
    """
    global _active
    if _active is not None:
        raise RuntimeError("virtual_time() cannot be nested")
    if clock is None:
        loop = asyncio.get_running_loop()
        if not isinstance(loop, VirtualEventLoop):
            raise RuntimeError(
                "virtual_time() needs a clock; pass one or run inside "
                "dst.run's VirtualEventLoop"
            )
        clock = loop.clock
    _active = clock
    saved: dict[str, Any] = {name: getattr(time, name) for name in _PATCHED_NAMES}

    def sleep_s(seconds: float) -> None:
        if seconds < 0:
            raise ValueError(f"sleep length must be non-negative, got {seconds}")
        clock.advance(seconds)

    def time_s() -> float:
        return clock.time()

    def time_ns_i() -> int:
        return int(clock.time() * 1_000_000_000)

    try:
        time.time = time_s  # type: ignore[assignment]
        time.monotonic = time_s  # type: ignore[assignment]
        time.perf_counter = time_s  # type: ignore[assignment]
        time.sleep = sleep_s  # type: ignore[assignment]
        time.time_ns = time_ns_i  # type: ignore[assignment]
        time.monotonic_ns = time_ns_i  # type: ignore[assignment]
        time.perf_counter_ns = time_ns_i  # type: ignore[assignment]
        yield clock
    finally:
        for name, original in saved.items():
            setattr(time, name, original)
        _active = None
