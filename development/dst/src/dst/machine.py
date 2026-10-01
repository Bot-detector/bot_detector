"""Virtual machine: cpu accounting, io delays and fault injection.

The machine is the resource model of "the box" a program runs on, as
seen from the virtual timeline:

- ``await machine.cpu(cost_s)`` models compute work on one serial
  core (capacity: 1.0 cpu-second per virtual second). Costs queue up
  FIFO, so a pump spending 0.0002s per message sustains at most
  5,000 msg/s and visibly falls behind a faster feed instead of
  running infinitely fast. Waiting happens in virtual time via
  ``asyncio.sleep``, so saturation replays deterministically.
- ``await machine.io(system, n_bytes=...)`` draws a latency from a
  per-system profile (mean ± uniform jitter, optional throughput for
  payload size) and can fail with a seeded probability. Unknown
  systems are configuration errors, not runtime faults.
- Faults: a seeded, percentage-based stall schedule (gc pause /
  process freeze shaped as extra seconds added to a cpu or io call),
  same design as perf's EventSchedule: one RNG, replay per seed.

Every draw comes from one RNG in a fixed order (stall -> fail ->
latency), and the virtual loop is single-threaded, so a run with the
same seed and call sequence replays exactly.
"""

import asyncio
import math
import random

from pydantic import BaseModel, ConfigDict, Field

from .clock import VirtualClock
from .loop import VirtualEventLoop


class IoConfig(BaseModel):
    """Latency profile for one named io system.

    Draws are ``mean_ms + uniform(-jitter_ms, +jitter_ms)`` clamped at
    zero. ``throughput_mbps`` (when set) adds ``n_bytes`` transfer time
    on top of the latency draw.
    """

    mean_ms: float = Field(gt=0.0)
    jitter_ms: float = Field(default=0.0, ge=0.0)
    fail_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    throughput_mbps: float | None = Field(default=None, gt=0.0)


class FaultSchedule(BaseModel):
    """Seeded stall schedule.

    stall_pct is a probability per cpu/io call, not a rate: at
    100 msg/s and stall_pct=1, a 0.1s stall eats ~10% of the machine.
    """

    seed: int = 0
    stall_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    stall_s: float = Field(default=0.1, ge=0.0)


class MachineConfig(BaseModel):
    """Machine configuration: io profiles and the fault schedule."""

    seed: int = 0
    io: dict[str, IoConfig] = Field(default_factory=dict)
    faults: FaultSchedule = Field(default_factory=FaultSchedule)


class CpuGrant(BaseModel):
    """Outcome of one cpu() call."""

    what: str
    cost_s: float
    waited_s: float
    stalled_s: float
    finished_s: float


class IoResult(BaseModel):
    """Outcome of one io() call; error carries the injected failure."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    system: str
    latency_s: float
    requested_bytes: int
    error: Exception | None = None


class IoError(Exception):
    """Seeded io failure surfaced as a value on IoResult."""


class VirtualMachine:
    """Resource model of one machine on the virtual timeline.

    Bind it to a clock explicitly, or construct it inside a
    ``dst.run`` scenario and it picks up the running VirtualEventLoop's
    clock (same convention as ``virtual_time``).
    """

    def __init__(self, config: MachineConfig, clock: VirtualClock | None = None):
        if clock is None:
            loop = asyncio.get_running_loop()
            if not isinstance(loop, VirtualEventLoop):
                raise RuntimeError(
                    "VirtualMachine needs a clock; pass one or construct "
                    "it inside dst.run's VirtualEventLoop"
                )
            clock = loop.clock
        self.config = config
        self.clock = clock
        self._rng = random.Random(config.seed)
        self._started_s = clock.time()
        self._cpu_free_s = clock.time()
        self.cpu_calls = 0
        self.cpu_busy_s = 0.0
        self.cpu_waited_s = 0.0
        self.io_calls = 0
        self.io_failures = 0
        self.io_latency_s = 0.0
        self.stalls = 0
        self.stall_s = 0.0

    async def cpu(self, cost_s: float, *, what: str = "") -> CpuGrant:
        """Run compute work on the serial core; waits when it is busy.

        cost_s is cpu-seconds on one core. Concurrent callers queue
        FIFO; the returned grant reports how long the call waited for
        the core (the saturation signal) and any injected stall.
        """
        _check_seconds(cost_s, "cost_s")
        stall = self._next_stall()
        now = self.clock.time()
        start_s = max(now, self._cpu_free_s)
        finished_s = start_s + cost_s + stall
        self._cpu_free_s = finished_s
        self.cpu_calls += 1
        self.cpu_busy_s += cost_s
        self.cpu_waited_s += start_s - now
        if finished_s > now:
            await asyncio.sleep(finished_s - now)
        return CpuGrant(
            what=what,
            cost_s=cost_s,
            waited_s=start_s - now,
            stalled_s=stall,
            finished_s=finished_s,
        )

    async def io(self, system: str, *, n_bytes: int = 0) -> IoResult:
        """Wait out an io operation against the named system profile.

        Draw order per call is fixed for replayability: stall roll,
        failure roll, latency draw. Transfer time from
        ``throughput_mbps`` is added after the latency draw.
        """
        profile = self.config.io.get(system)
        if profile is None:
            raise ValueError(
                f"unknown io system {system!r}; configured: {sorted(self.config.io)}"
            )
        if n_bytes < 0:
            raise ValueError(f"n_bytes must be >= 0, got {n_bytes}")
        self.io_calls += 1
        stall = self._next_stall()
        roll = self._rng.random() * 100.0
        error: Exception | None = None
        if roll < profile.fail_pct:
            self.io_failures += 1
            error = IoError(f"io on {system!r} failed (seeded)")
        latency_s = max(
            0.0,
            profile.mean_ms / 1000.0
            + self._rng.uniform(-profile.jitter_ms, profile.jitter_ms) / 1000.0,
        )
        if profile.throughput_mbps is not None and n_bytes > 0:
            latency_s += n_bytes * 8.0 / (profile.throughput_mbps * 1_000_000.0)
        latency_s += stall
        self.io_latency_s += latency_s
        if latency_s > 0.0:
            await asyncio.sleep(latency_s)
        return IoResult(
            system=system, latency_s=latency_s, requested_bytes=n_bytes, error=error
        )

    def load_s(self) -> float:
        """Queued cpu work in virtual seconds (0 = idle core)."""
        return max(0.0, self._cpu_free_s - self.clock.time())

    def utilization(self) -> float:
        """Fraction of elapsed virtual time the core was busy."""
        elapsed = self.clock.time() - self._started_s
        if elapsed <= 0.0:
            return 0.0
        return min(1.0, self.cpu_busy_s / elapsed)

    def _next_stall(self) -> float:
        roll = self._rng.random() * 100.0
        if roll < self.config.faults.stall_pct:
            self.stalls += 1
            self.stall_s += self.config.faults.stall_s
            return self.config.faults.stall_s
        return 0.0


def _check_seconds(value: float, name: str) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite, got {value!r}")
    if value < 0.0:
        raise ValueError(f"{name} must be >= 0, got {value}")
