"""Disk subsystem: latency and failures."""

import asyncio

from .config import DiskConfig
from .processes import Processes
from .randomness import Randomness
from .results import IoError, IoResult


class Disk:
    """Local disk on the virtual timeline.

    Draw order per operation is fixed for replayability: process stall
    roll, failure roll, latency jitter.
    """

    def __init__(
        self, config: DiskConfig, rng: Randomness, processes: Processes
    ) -> None:
        self.config = config
        self._rng = rng
        self._processes = processes
        self.calls = 0
        self.failures = 0
        self.latency_s = 0.0

    async def read(self, n_bytes: int = 0) -> IoResult:
        """Wait out one disk read; failures come back as values."""
        return await self._op(n_bytes, "read")

    async def write(self, n_bytes: int = 0) -> IoResult:
        """Wait out one disk write; failures come back as values."""
        return await self._op(n_bytes, "write")

    async def _op(self, n_bytes: int, op: str) -> IoResult:
        if n_bytes < 0:
            raise ValueError(f"n_bytes must be >= 0, got {n_bytes}")
        self.calls += 1
        stall = self._processes.roll_stall()
        roll = self._rng.random() * 100.0
        error: Exception | None = None
        if roll < self.config.fail_pct:
            self.failures += 1
            error = IoError(f"disk {op} failed (seeded)")
        latency_s = max(
            0.0,
            self.config.mean_ms / 1000.0
            + self._rng.uniform(-self.config.jitter_ms, self.config.jitter_ms) / 1000.0,
        )
        latency_s += stall
        self.latency_s += latency_s
        if latency_s > 0.0:
            await asyncio.sleep(latency_s)
        return IoResult(
            system="disk", latency_s=latency_s, requested_bytes=n_bytes, error=error
        )
