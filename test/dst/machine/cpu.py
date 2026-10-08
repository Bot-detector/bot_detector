"""CPU subsystem: serial work accounting with background load."""

import asyncio
import math

from ..clock import VirtualClock
from .config import CpuConfig
from .processes import Processes
from .results import CpuGrant


def _check_seconds(value: float, name: str) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite, got {value!r}")
    if value < 0.0:
        raise ValueError(f"{name} must be >= 0, got {value}")


class Cpu:
    """Serial core model on the virtual timeline.

    Capacity is ``cores`` cpu-seconds per virtual second. ``work()``
    queues up FIFO, so a pump spending 0.0002s per message sustains at
    most 5,000 msg/s per core and visibly falls behind a faster feed.
    ``set_load()`` models steady background load (other processes): it
    shrinks the effective capacity to ``cores * (1 - load)``.
    """

    def __init__(
        self, config: CpuConfig, clock: VirtualClock, processes: Processes
    ) -> None:
        self.config = config
        self._clock = clock
        self._processes = processes
        self._load = 0.0
        self._started_s = clock.time()
        self._free_s = clock.time()
        self._load_mark_s = clock.time()
        self._load_accum_s = 0.0
        self.calls = 0
        self.busy_s = 0.0
        self.waited_s = 0.0

    @property
    def cores(self) -> int:
        return self.config.cores

    @property
    def load(self) -> float:
        """Current background load fraction in [0, 1)."""
        return self._load

    def set_load(self, load: float) -> None:
        """Set persistent background load; capacity becomes cores*(1-load).

        Rejected at 1.0 because that would starve real work forever.
        Load changes are integrated exactly, so ``utilization()``
        stays replayable across calls.
        """
        if not math.isfinite(load) or not 0.0 <= load < 1.0:
            raise ValueError(f"load must be in [0, 1), got {load!r}")
        now_s = self._clock.time()
        self._load_accum_s += self._load * (now_s - self._load_mark_s)
        self._load_mark_s = now_s
        self._load = load

    def clear_load(self) -> None:
        """Drop the background load back to zero."""
        self.set_load(0.0)

    async def work(self, cost_s: float, *, what: str = "") -> CpuGrant:
        """Run compute work on the cores; waits when they are busy.

        cost_s is cpu-seconds total. Concurrent callers queue FIFO;
        the returned grant reports how long the call waited (the
        saturation signal) and any injected process stall.
        """
        _check_seconds(cost_s, "cost_s")
        stall = self._processes.roll_stall()
        now = self._clock.time()
        duration_s = cost_s / (self.config.cores * (1.0 - self._load)) + stall
        start_s = max(now, self._free_s)
        finished_s = start_s + duration_s
        self._free_s = finished_s
        self.calls += 1
        self.busy_s += cost_s
        self.waited_s += start_s - now
        if finished_s > now:
            await asyncio.sleep(finished_s - now)
        return CpuGrant(
            what=what,
            cost_s=cost_s,
            waited_s=start_s - now,
            stalled_s=stall,
            finished_s=finished_s,
        )

    def queued_s(self) -> float:
        """Queued cpu work in virtual seconds (0 = idle cores)."""
        return max(0.0, self._free_s - self._clock.time())

    def utilization(self) -> float:
        """Fraction of elapsed virtual time the cores were busy.

        Counts real work plus integrated background load.
        """
        now_s = self._clock.time()
        elapsed = now_s - self._started_s
        if elapsed <= 0.0:
            return 0.0
        load_accum_s = self._load_accum_s + self._load * (now_s - self._load_mark_s)
        return min(1.0, (self.busy_s + load_accum_s) / elapsed)
