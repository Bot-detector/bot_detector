"""Counter-based fault draws: pure, order-free, shard-safe.

Every fault decision derives from blake2b over ``(seed, stream,
ordinal)``. The same triple yields the same outcome forever, in any
draw order, in any process — no shared RNG state, so millions of ops
across parallel shards stay reproducible (spec §4.1).

``draw`` primes one blake2b per ``(seed, stream)`` prefix and copies it
per call (hash streaming: ``blake2b(prefix + suffix)`` equals
``primed.copy().update(suffix)``), so draws are byte-identical to
hashing the full triple each time — just cheaper on million-op runs.
"""

from hashlib import blake2b
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

DRAW_MAX = 2**64

# primed prefix hashers keyed by (seed, stream); hash state is shared
# and immutable by convention — callers must ``.copy()`` before update.
# Streams per process are few (fault streams, topics x partitions), so
# the cache is unbounded.
_PRIMED: dict[tuple[int, str], Any] = {}


def _primed(seed: int, stream: str) -> Any:
    """Primed blake2b over the ``f"{seed}:{stream}:"`` prefix."""
    key = (seed, stream)
    h = _PRIMED.get(key)
    if h is None:
        h = blake2b(f"{seed}:{stream}:".encode(), digest_size=8)
        _PRIMED[key] = h
    return h


def draw(seed: int, stream: str, ordinal: int) -> float:
    """Draw one uniform float in [0, 1) from the counter-based engine.

    Args:
        seed: Run-level seed everything derives from.
        stream: Fault stream id, e.g. ``"k:p:<topic>:<part>"``.
        ordinal: Per-stream op counter supplied by the state layer.

    Returns:
        Uniform float in [0, 1).
    """
    h = _primed(seed, stream).copy()
    h.update(str(ordinal).encode())
    return int.from_bytes(h.digest(), "big") / DRAW_MAX


def bucket(draw_value: float, *pcts: float) -> int:
    """Resolve a draw against cumulative fault buckets.

    Args:
        draw_value: Uniform float in [0, 1) from :func:`draw`.
        pcts: Bucket percentages in the documented draw order for the
            surface (spec §3 tables). Each pct is a share of [0, 100).

    Returns:
        Index of the bucket the draw lands in, or ``-1`` when the draw
        falls past every bucket (no fault).
    """
    edge = 0.0
    for index, pct in enumerate(pcts):
        edge += pct
        if draw_value * 100.0 < edge:
            return index
    return -1


class KafkaFaultConfig(BaseModel):
    """Pct knobs for broker faults (spec §3.2), draw order fixed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    produce_buffer_timeout_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    produce_closed_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    fetch_timeout_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    consumer_stopped_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    poison_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    slow_fetch_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    slow_fetch_s: float = Field(default=1.0, ge=0.0)
    commit_fail_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    commit_timeout_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    outage_pct: float = Field(default=0.0, ge=0.0, le=100.0)

    @model_validator(mode="after")
    def _groups_within_budget(self) -> "KafkaFaultConfig":
        produce = self.produce_buffer_timeout_pct + self.produce_closed_pct
        fetch = (
            self.fetch_timeout_pct
            + self.consumer_stopped_pct
            + self.poison_pct
            + self.slow_fetch_pct
        )
        commit = self.commit_fail_pct + self.commit_timeout_pct
        for name, total in (("produce", produce), ("fetch", fetch), ("commit", commit)):
            if total > 100.0:
                raise ValueError(f"{name} fault pcts must sum to <= 100, got {total}")
        return self


class DbFaultConfig(BaseModel):
    """Pct knobs for statement faults (spec §3.3), draw order fixed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    deadlock_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    lock_wait_timeout_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    conn_lost_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    too_many_conn_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    temp_table_full_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    dup_key_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    pool_timeout_pct: float = Field(default=0.0, ge=0.0, le=100.0)

    @model_validator(mode="after")
    def _statements_within_budget(self) -> "DbFaultConfig":
        statements = (
            self.deadlock_pct
            + self.lock_wait_timeout_pct
            + self.conn_lost_pct
            + self.too_many_conn_pct
            + self.temp_table_full_pct
            + self.dup_key_pct
        )
        if statements > 100.0:
            raise ValueError(
                f"statement fault pcts must sum to <= 100, got {statements}"
            )
        return self


class JagexFaultConfig(BaseModel):
    """Pct knobs for HTTP surface faults (spec §3.4), draw order fixed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    not_found_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    redirect_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    server_error_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    timeout_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    poison_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    private_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    proxy_ban_pct: float = Field(default=0.0, ge=0.0, le=100.0)

    @model_validator(mode="after")
    def _requests_within_budget(self) -> "JagexFaultConfig":
        total = (
            self.not_found_pct
            + self.redirect_pct
            + self.server_error_pct
            + self.timeout_pct
            + self.poison_pct
            + self.private_pct
        )
        if total > 100.0:
            raise ValueError(f"request fault pcts must sum to <= 100, got {total}")
        return self


class FaultConfig(BaseModel):
    """Per-system fault tables wired from the spec §3 knob sets."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kafka: KafkaFaultConfig = Field(default_factory=KafkaFaultConfig)
    db: DbFaultConfig = Field(default_factory=DbFaultConfig)
    jagex: JagexFaultConfig = Field(default_factory=JagexFaultConfig)
