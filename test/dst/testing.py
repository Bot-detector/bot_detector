"""Scorecard models and replay checker (spec section 6, E1-slim + E2).

A scenario returns a ``Scorecard``; ``report_bytes`` renders it to
canonical bytes for the CI replay gate, ``hard_gate`` applies the
invariant gate (any failed invariant forces score 0), and
``replay_check`` runs a scenario twice via ``dst.run`` and requires
byte-equal reports.
"""

import orjson
from collections.abc import Callable, Coroutine
from typing import Any

from pydantic import BaseModel, Field

from .runner import run


class Invariant(BaseModel):
    """One binary, stably named correctness property."""

    name: str
    ok: bool
    detail: str = ""


class Subscores(BaseModel):
    """Normalized 0..1 performance subscores (MVP-slim set)."""

    loss: float = 0.0
    keep_up: float = 0.0
    drain: float = 0.0


class Scorecard(BaseModel):
    """Seeded scenario report for hill climbing."""

    seed: int
    counters: dict[str, int]
    invariants: list[Invariant]
    subscores: Subscores = Field(default_factory=Subscores)
    score: float = 0.0


def report_bytes(scorecard: Scorecard) -> bytes:
    """Serialize canonically: sorted keys, compact, byte-stable."""

    return orjson.dumps(scorecard.model_dump(mode="json"), option=orjson.OPT_SORT_KEYS)


def invariants_failed(scorecard: Scorecard) -> list[str]:
    """Names of invariants that failed."""

    return [invariant.name for invariant in scorecard.invariants if not invariant.ok]


def hard_gate(scorecard: Scorecard) -> float:
    """Score with the invariant gate applied: any failure forces 0.0."""

    if invariants_failed(scorecard):
        return 0.0
    return scorecard.score


def replay_check(
    scenario_factory: Callable[[], Coroutine[Any, Any, Scorecard]],
    seed_label: int | None = None,
) -> tuple[bytes, bytes]:
    """Run the scenario twice and require byte-equal reports.

    Takes a factory because ``dst.run`` consumes a coroutine object, so
    each run needs a fresh one. The coroutine's return value must be a
    ``Scorecard``. Raises ``AssertionError`` naming the first differing
    field (or byte offset) on mismatch.
    """

    label = f"seed {seed_label}" if seed_label is not None else "scenario"
    reports: list[bytes] = []
    for i in (1, 2):
        result = run(scenario_factory())
        if result.error is not None or not result.done:
            raise AssertionError(
                f"replay run {i} ({label}) did not complete: "
                f"done={result.done}, error={result.error!r}"
            )
        if not isinstance(result.value, Scorecard):
            raise AssertionError(
                f"replay run {i} ({label}) returned "
                f"{type(result.value).__name__}, expected Scorecard"
            )
        reports.append(report_bytes(result.value))
    first, second = reports
    if first == second:
        return first, second
    raise AssertionError(
        f"reports differ for {label}: {_first_difference(first, second)}"
    )


def _first_difference(a: bytes, b: bytes) -> str:
    """Locate the first divergence: field path if parseable, else offset."""

    offset = next(
        (i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b))
    )
    try:
        doc_a: Any = orjson.loads(a)
        doc_b: Any = orjson.loads(b)
    except orjson.JSONDecodeError:
        return f"byte offset {offset}"
    return f"{_diff_path(doc_a, doc_b, '$')} (byte offset {offset})"


def _diff_path(a: Any, b: Any, path: str) -> str:
    """First differing field path between two parsed report documents."""

    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b)):
            if key not in a or key not in b:
                side = "a" if key not in a else "b"
                return f"{path}.{key} missing in {side}"
            if a[key] != b[key]:
                return _diff_path(a[key], b[key], f"{path}.{key}")
        return path
    if isinstance(a, list) and isinstance(b, list):
        for i, (x, y) in enumerate(zip(a, b)):
            if x != y:
                return _diff_path(x, y, f"{path}[{i}]")
        return f"{path} length {len(a)} != {len(b)}"
    return f"{path} {a!r} != {b!r}"
