"""Memory subsystem: RAM accounting and pressure."""

from .config import MemoryConfig


class Memory:
    """Byte-level RAM model: consume, release, pressure.

    Accounting only: pressure is a signal scenarios and reports read,
    it does not slow anything down by itself (use process stalls or
    cpu load for performance effects). Overcommit is a loud error, not
    a silent swap.
    """

    def __init__(self, config: MemoryConfig) -> None:
        self.config = config
        self.used_bytes = 0
        self.peak_bytes = 0
        self.consumes = 0
        self.releases = 0

    @property
    def total_bytes(self) -> int:
        return self.config.total_bytes

    @property
    def free_bytes(self) -> int:
        return self.config.total_bytes - self.used_bytes

    @property
    def pressure(self) -> float:
        """Used fraction of total, clamped to [0, 1]."""
        return min(1.0, self.used_bytes / self.config.total_bytes)

    def consume(self, n_bytes: int) -> None:
        """Allocate n_bytes; out-of-memory raises instead of swapping."""
        if n_bytes < 0:
            raise ValueError(f"n_bytes must be >= 0, got {n_bytes}")
        if self.used_bytes + n_bytes > self.config.total_bytes:
            raise ValueError(
                f"out of memory: requested {n_bytes} bytes with "
                f"{self.free_bytes} free of {self.config.total_bytes}"
            )
        self.used_bytes += n_bytes
        self.peak_bytes = max(self.peak_bytes, self.used_bytes)
        self.consumes += 1

    def release(self, n_bytes: int) -> None:
        """Free n_bytes; releasing more than is used is an error."""
        if n_bytes < 0:
            raise ValueError(f"n_bytes must be >= 0, got {n_bytes}")
        if n_bytes > self.used_bytes:
            raise ValueError(
                f"cannot release {n_bytes} bytes, only {self.used_bytes} in use"
            )
        self.used_bytes -= n_bytes
        self.releases += 1
