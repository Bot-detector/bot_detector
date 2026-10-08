"""Outcome models for machine operations."""

from pydantic import BaseModel, ConfigDict


class CpuGrant(BaseModel):
    """Outcome of one cpu.work() call."""

    what: str
    cost_s: float
    waited_s: float
    stalled_s: float
    finished_s: float


class IoResult(BaseModel):
    """Outcome of one network/disk operation; error carries the failure."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    system: str
    latency_s: float
    requested_bytes: int
    error: Exception | None = None


class IoError(Exception):
    """Seeded io failure surfaced as a value on IoResult."""
