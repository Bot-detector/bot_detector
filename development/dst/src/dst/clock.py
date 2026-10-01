"""Virtual clock: the single source of simulated time.

Every part of the DST (event loop timers, sync time patches, machine
accounting) reads time from here, so a scenario has exactly one
timeline. The clock is strictly monotonic: time never moves backwards,
and ``advance_to`` clamps to the current time.
"""

import math


class VirtualClock:
    """Monotonic simulated clock.

    Time is a float of seconds starting at ``start_s`` (default 0).
    ``advance`` moves by a relative amount, ``advance_to`` jumps forward
    to an absolute deadline; both are O(1) wall-clock work regardless of
    the simulated duration.
    """

    def __init__(self, start_s: float = 0.0) -> None:
        if not math.isfinite(start_s):
            raise ValueError(f"start_s must be finite, got {start_s!r}")
        if start_s < 0:
            raise ValueError(f"start_s must be >= 0, got {start_s}")
        self._now_s = start_s
        self.jumps = 0

    @property
    def now_s(self) -> float:
        return self._now_s

    def time(self) -> float:
        return self._now_s

    def advance(self, seconds: float) -> float:
        """Move forward by ``seconds`` and return the new time."""
        if not math.isfinite(seconds):
            raise ValueError(f"seconds must be finite, got {seconds!r}")
        if seconds < 0:
            raise ValueError(f"cannot advance backwards by {seconds}s")
        if seconds > 0:
            self._now_s += seconds
            self.jumps += 1
        return self._now_s

    def advance_to(self, when_s: float) -> float:
        """Jump forward to ``when_s`` (no-op if it is in the past)."""
        if not math.isfinite(when_s):
            raise ValueError(f"when_s must be finite, got {when_s!r}")
        return self.advance(max(0.0, when_s - self._now_s))
