import asyncio
import math

from ..faults import draw


class LinkError(Exception):
    """Seeded link loss returned as a value, never raised."""


class LinkCosts:
    """One simulated network link: latency, bandwidth, seeded loss.

    Per fetch, one draw resolves the loss roll (``{stream}:loss``) and
    one the jitter (``{stream}:latency``), both at the same attempt
    ordinal: latency is ``mean_ms + uniform(-jitter_ms, +jitter_ms)``
    clamped at zero, plus ``n_bytes`` transfer time at
    ``bandwidth_mbps`` when set. A lost fetch still pays its latency
    (the RTT elapses, then the error surfaces as a value).
    """

    def __init__(
        self,
        *,
        seed: int,
        stream: str,
        mean_ms: float = 0.01,
        jitter_ms: float = 0.005,
        bandwidth_mbps: float | None = None,
        loss_pct: float = 0.0,
    ) -> None:
        for name, value in (("mean_ms", mean_ms), ("jitter_ms", jitter_ms)):
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite >= 0, got {value!r}")
        if bandwidth_mbps is not None and (
            not math.isfinite(bandwidth_mbps) or bandwidth_mbps <= 0.0
        ):
            raise ValueError(
                f"bandwidth_mbps must be finite > 0, got {bandwidth_mbps!r}"
            )
        if not math.isfinite(loss_pct) or not 0.0 <= loss_pct <= 100.0:
            raise ValueError(f"loss_pct must be finite in [0, 100], got {loss_pct!r}")
        assert isinstance(stream, str) and stream, "stream must be a non-empty name"
        self._seed = seed
        self._stream = stream
        self._mean_ms = mean_ms
        self._jitter_ms = jitter_ms
        self._bandwidth_mbps = bandwidth_mbps
        self._loss_pct = loss_pct
        self._ordinal = 0
        self.calls = 0
        self.failures = 0
        self.latency_s = 0.0

    async def fetch(self, n_bytes: int = 0) -> Exception | None:
        """Wait out one link round trip; seeded loss returns as a value.

        Returns ``None`` on delivery, or the :class:`LinkError` for a
        seeded loss (the latency is paid either way).
        """
        if n_bytes < 0:
            raise ValueError(f"n_bytes must be >= 0, got {n_bytes}")
        latency_s, error = self.draw(n_bytes)
        self.calls += 1
        if error is not None:
            self.failures += 1
        if latency_s > 0.0:
            await asyncio.sleep(latency_s)
        assert error is None or isinstance(error, LinkError)
        return error

    def draw(self, n_bytes: int) -> tuple[float, Exception | None]:
        """Resolve one attempt without sleeping: ``(latency_s, error)``.

        Fixed draw order per attempt ordinal: loss roll first, jitter
        second, each on its own stream so knob changes on one never
        shift the other.
        """
        assert n_bytes >= 0, f"n_bytes must be >= 0, got {n_bytes}"
        ordinal = self._ordinal
        self._ordinal += 1
        loss = draw(self._seed, f"{self._stream}:loss", ordinal) * 100.0
        error: Exception | None = (
            LinkError("link lost (seeded)") if loss < self._loss_pct else None
        )
        jitter = draw(self._seed, f"{self._stream}:latency", ordinal)
        latency_ms = self._mean_ms + (jitter * 2.0 - 1.0) * self._jitter_ms
        latency_s = max(0.0, latency_ms / 1000.0)
        if self._bandwidth_mbps is not None and n_bytes > 0:
            latency_s += n_bytes * 8.0 / (self._bandwidth_mbps * 1_000_000.0)
        assert latency_s >= 0.0, f"latency went negative: {latency_s!r}"
        self.latency_s += latency_s
        return latency_s, error


class CpuCosts:
    """Fake-owned virtual work: a sleep per call plus call/busy counters.

    Concurrent calls overlap (no FIFO serialization between workers).
    Every call counts, including zero-cost ones (a call is an event
    even when it is free); the busy total is what utilization math
    reads off the fake.
    """

    def __init__(self) -> None:
        self.calls = 0
        self.busy_s = 0.0

    async def work(self, cost_s: float) -> None:
        """Charge ``cost_s`` cpu-seconds as one virtual sleep."""
        if not math.isfinite(cost_s) or cost_s < 0.0:
            raise ValueError(f"cost_s must be finite >= 0, got {cost_s!r}")
        self.calls += 1
        self.busy_s += cost_s
        if cost_s > 0.0:
            await asyncio.sleep(cost_s)
        assert self.busy_s >= 0.0
