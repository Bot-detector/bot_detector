"""Machine configuration: one config model per subsystem."""

from pydantic import BaseModel, Field

from ..units import GB


class CpuConfig(BaseModel):
    """Core count; capacity is ``cores`` cpu-seconds per virtual second."""

    cores: int = Field(default=1, ge=1)


class MemoryConfig(BaseModel):
    """Installed RAM; consuming beyond it is an error, not a swap."""

    total_bytes: int = Field(default=4 * GB, gt=0)


class NetworkConfig(BaseModel):
    """Egress profile: latency, bandwidth, packet loss.

    Latency draws are ``mean_ms + uniform(-jitter_ms, +jitter_ms)``
    clamped at zero. ``bandwidth_mbps`` (when set) adds ``n_bytes``
    transfer time on top of the latency draw.
    """

    mean_ms: float = Field(default=1.0, gt=0.0)
    jitter_ms: float = Field(default=0.0, ge=0.0)
    packet_loss_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    bandwidth_mbps: float | None = Field(default=None, gt=0.0)


class DiskConfig(BaseModel):
    """Local disk profile: latency and failure rate."""

    mean_ms: float = Field(default=5.0, gt=0.0)
    jitter_ms: float = Field(default=0.0, ge=0.0)
    fail_pct: float = Field(default=0.0, ge=0.0, le=100.0)


class ProcessConfig(BaseModel):
    """Background-process stall schedule (gc pause / freeze shaped).

    stall_pct is a probability per cpu/network/disk operation, not a
    rate: at 100 msg/s and stall_pct=1, a 0.1s stall eats ~10% of the
    machine.
    """

    stall_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    stall_s: float = Field(default=0.1, ge=0.0)


class MachineConfig(BaseModel):
    """Machine configuration: per-subsystem configs and the seed.

    One seed drives every subsystem draw through one Randomness in a
    fixed order, so a run replays exactly.
    """

    seed: int = 0
    cpu: CpuConfig = Field(default_factory=CpuConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    disk: DiskConfig = Field(default_factory=DiskConfig)
    processes: ProcessConfig = Field(default_factory=ProcessConfig)
