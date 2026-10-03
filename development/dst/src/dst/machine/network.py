"""Network subsystem: latency, bandwidth, packet loss, partitions."""

import asyncio

from .config import NetworkConfig
from .processes import Processes
from .randomness import Randomness
from .results import IoError, IoResult


class Network:
    """Egress to the outside world on the virtual timeline.

    Draw order per fetch is fixed for replayability: process stall
    roll, packet-loss roll, latency jitter. Transfer time from
    ``bandwidth_mbps`` is added after the jitter draw. A partition
    fails fetches immediately as values and consumes no draws, so
    partitioning cannot shift the RNG stream of a run.
    """

    def __init__(
        self, config: NetworkConfig, rng: Randomness, processes: Processes
    ) -> None:
        self.config = config
        self._rng = rng
        self._processes = processes
        self._partitioned = False
        self.calls = 0
        self.failures = 0
        self.latency_s = 0.0

    @property
    def partitioned(self) -> bool:
        return self._partitioned

    def partition(self) -> None:
        """Sever the network: every fetch fails until ``heal()``."""
        self._partitioned = True

    def heal(self) -> None:
        """Restore the network after a partition."""
        self._partitioned = False

    async def fetch(self, n_bytes: int = 0) -> IoResult:
        """Wait out one network round trip; failures come back as values."""
        if n_bytes < 0:
            raise ValueError(f"n_bytes must be >= 0, got {n_bytes}")
        self.calls += 1
        if self._partitioned:
            self.failures += 1
            return IoResult(
                system="network",
                latency_s=0.0,
                requested_bytes=n_bytes,
                error=IoError("network partitioned"),
            )
        stall = self._processes.roll_stall()
        roll = self._rng.random() * 100.0
        error: Exception | None = None
        if roll < self.config.packet_loss_pct:
            self.failures += 1
            error = IoError("packet lost (seeded)")
        latency_s = max(
            0.0,
            self.config.mean_ms / 1000.0
            + self._rng.uniform(-self.config.jitter_ms, self.config.jitter_ms) / 1000.0,
        )
        if self.config.bandwidth_mbps is not None and n_bytes > 0:
            latency_s += n_bytes * 8.0 / (self.config.bandwidth_mbps * 1_000_000.0)
        latency_s += stall
        self.latency_s += latency_s
        if latency_s > 0.0:
            await asyncio.sleep(latency_s)
        return IoResult(
            system="network", latency_s=latency_s, requested_bytes=n_bytes, error=error
        )
