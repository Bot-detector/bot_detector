"""dst.testing: scorecard helpers and the replay checker (E1-slim + E2)."""

import asyncio
import random
import time
from collections.abc import Callable, Coroutine
from typing import Any

import pytest
import orjson

from dst.testing import (
    Invariant,
    Scorecard,
    Subscores,
    hard_gate,
    invariants_failed,
    replay_check,
    report_bytes,
)


def _ok_scorecard(counters: dict[str, int] | None = None) -> Scorecard:
    return Scorecard(
        seed=7,
        counters=counters if counters is not None else {"produced": 10},
        invariants=[
            Invariant(name="no_loss", ok=True),
            Invariant(name="drained", ok=True),
        ],
        subscores=Subscores(loss=1.0, keep_up=0.9, drain=0.8),
        score=0.9,
    )


def test_hard_gate_returns_score_when_all_invariants_ok():
    assert hard_gate(_ok_scorecard()) == 0.9


def test_hard_gate_returns_zero_when_any_invariant_fails():
    scorecard = _ok_scorecard()
    scorecard.invariants.append(Invariant(name="no_dupes", ok=False))
    assert hard_gate(scorecard) == 0.0


def test_invariants_failed_lists_names():
    scorecard = _ok_scorecard()
    scorecard.invariants.append(Invariant(name="no_dupes", ok=False))
    scorecard.invariants.append(Invariant(name="no_gap", ok=False))
    assert invariants_failed(scorecard) == ["no_dupes", "no_gap"]


def test_invariants_failed_empty_when_all_ok():
    assert invariants_failed(_ok_scorecard()) == []


def test_report_bytes_identical_for_equal_scorecards():
    assert report_bytes(_ok_scorecard()) == report_bytes(_ok_scorecard())


def test_report_bytes_ignores_counter_insertion_order():
    a = report_bytes(_ok_scorecard({"produced": 10, "consumed": 9}))
    b = report_bytes(_ok_scorecard({"consumed": 9, "produced": 10}))
    assert a == b


def _seeded_scenario(seed: int) -> Callable[[], Coroutine[Any, Any, Scorecard]]:
    """Scenario whose report derives only from the seed (deterministic)."""

    def factory() -> Coroutine[Any, Any, Scorecard]:
        async def scenario() -> Scorecard:
            rng = random.Random(seed)
            await asyncio.sleep(0.25)
            produced = rng.randrange(100, 200)
            return Scorecard(
                seed=seed,
                counters={"produced": produced, "consumed": produced},
                invariants=[Invariant(name="no_loss", ok=True)],
                subscores=Subscores(loss=1.0, keep_up=1.0, drain=1.0),
                score=1.0,
            )

        return scenario()

    return factory


def _jittered_factory() -> Coroutine[Any, Any, Scorecard]:
    """Scenario that leaks wall-clock noise into its counters."""

    async def scenario() -> Scorecard:
        return Scorecard(
            seed=7,
            counters={"jitter": time.perf_counter_ns()},
            invariants=[],
            score=0.5,
        )

    return scenario()


def test_replay_check_passes_on_deterministic_seeded_scenario():
    first, second = replay_check(_seeded_scenario(42), seed_label=42)
    assert first == second
    assert (
        orjson.loads(first)["counters"]["consumed"]
        == orjson.loads(first)["counters"]["produced"]
    )


def test_replay_check_fails_on_injected_nondeterminism():
    with pytest.raises(AssertionError, match=r"counters"):
        replay_check(_jittered_factory, seed_label=7)
