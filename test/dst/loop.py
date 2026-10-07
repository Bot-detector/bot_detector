"""Virtual asyncio event loop: timers run on simulated time.

``VirtualEventLoop`` subclasses ``BaseSelectorEventLoop`` and replaces
only the time source and the I/O poll:

- ``time()`` returns the virtual clock, so ``call_later`` /
  ``call_at`` / ``asyncio.sleep`` / ``wait_for`` timeouts all schedule
  against simulated time. A coroutine sleeping 3600s finishes after a
  single O(1) clock jump.
- ``_run_once`` never polls the selector. When nothing is ready it
  jumps the clock to the next timer deadline instead of blocking.
  When there are no ready callbacks and no timers, the loop is parked
  on something that will never fire on a virtual timeline (real I/O,
  an unset future, a missing simulated system) and raises
  ``DSTIdleError`` so scenarios fail loudly instead of hanging.

Coroutines need no changes: standard ``await asyncio.sleep(n)``,
``asyncio.gather``, queues, locks and timeouts behave identically,
just in virtual time.
"""

import asyncio.base_events
import asyncio.selector_events
import heapq
from collections import deque
from typing import Final

from .clock import VirtualClock

# compaction thresholds from asyncio.base_events; getattr because they
# are private stdlib constants hidden from type checkers
_MIN_SCHEDULED_TIMER_HANDLES: Final[int] = getattr(
    asyncio.base_events, "_MIN_SCHEDULED_TIMER_HANDLES", 100
)
_MIN_CANCELLED_FRACTION: Final[float] = getattr(
    asyncio.base_events, "_MIN_CANCELLED_TIMER_HANDLES_FRACTION", 0.5
)


class DSTIdleError(RuntimeError):
    """Raised when the virtual loop has no work and no timers left.

    On a real loop this is where it would block on I/O forever. Under
    simulation that is always a bug in the scenario (a dependency on a
    real socket, a future nobody resolves, a simulated system that was
    not wired in).
    """


def running_clock() -> VirtualClock:
    """The clock of the running VirtualEventLoop.

    Simulated objects (Machine, FirehoseHub, ...) bind to it when
    constructed inside a ``dst.run`` scenario instead of demanding a
    clock argument everywhere.
    """
    loop = asyncio.get_running_loop()
    if not isinstance(loop, VirtualEventLoop):
        raise RuntimeError(
            "no virtual clock is running; pass a clock explicitly or "
            "construct inside dst.run's VirtualEventLoop"
        )
    return loop.clock


class VirtualEventLoop(asyncio.selector_events.BaseSelectorEventLoop):
    """Selector event loop whose clock and timers are simulated.

    Real socket I/O is deliberately unavailable: transports need a real
    peer, and the simulated world is provided by DST machines and fake
    systems instead. Anything that would block on I/O surfaces as
    ``DSTIdleError``.
    """

    def __init__(self, clock: VirtualClock, *, selector=None) -> None:
        super().__init__(selector=selector)
        self._clock = clock

    @property
    def clock(self) -> VirtualClock:
        return self._clock

    def time(self) -> float:
        return self._clock.time()

    def _run_once(self) -> None:
        # stdlib internals: real attributes, hidden by typeshed
        ready: deque[asyncio.Handle] = self._ready  # type: ignore[attr-defined]
        scheduled: list[asyncio.TimerHandle] = self._scheduled  # type: ignore[attr-defined]

        # compact cancelled timers exactly like the base loop
        if (
            len(scheduled) > _MIN_SCHEDULED_TIMER_HANDLES
            and self._timer_cancelled_count / len(scheduled)  # type: ignore[has-type]
            > _MIN_CANCELLED_FRACTION
        ):
            live = [h for h in scheduled if not h._cancelled]
            for timer in scheduled:
                if timer._cancelled:
                    timer._scheduled = False  # type: ignore[attr-defined]
            heapq.heapify(live)
            scheduled.clear()
            scheduled.extend(live)
            self._timer_cancelled_count = 0  # type: ignore[has-type]
        else:
            while scheduled and scheduled[0]._cancelled:
                self._timer_cancelled_count -= 1  # type: ignore[has-type]
                timer = heapq.heappop(scheduled)
                timer._scheduled = False  # type: ignore[attr-defined]

        # the virtual "I/O poll": instead of blocking on the selector,
        # fast-forward the clock so the next timer becomes due now
        if not ready:
            self._fast_forward()

        # pop every timer due at the current virtual time, in order
        now = self._clock.time()
        while scheduled and scheduled[0]._when <= now:  # type: ignore[attr-defined]
            timer = heapq.heappop(scheduled)
            timer._scheduled = False  # type: ignore[attr-defined]
            ready.append(timer)

        # run only what is ready now; callbacks scheduled by these run
        # on the next iteration (same contract as the base loop)
        ntodo = len(ready)
        for _ in range(ntodo):
            handle = ready.popleft()
            if handle._cancelled:
                continue
            if self._debug:  # type: ignore[attr-defined]
                try:
                    self._current_handle = handle  # type: ignore[attr-defined]
                    handle._run()
                finally:
                    self._current_handle = None  # type: ignore[attr-defined,assignment]
            else:
                handle._run()

    def _fast_forward(self) -> None:
        """Advance the clock to the next timer; idle with none = bug."""
        scheduled: list[asyncio.TimerHandle] = self._scheduled  # type: ignore[attr-defined]
        if not scheduled:
            raise DSTIdleError(
                "virtual loop is idle: no ready callbacks and no timers; "
                "a task is parked on real I/O or a future that never fires"
            )
        self._clock.advance_to(scheduled[0]._when)  # type: ignore[attr-defined]
