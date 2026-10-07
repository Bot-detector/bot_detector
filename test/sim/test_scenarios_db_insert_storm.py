"""db_insert_storm scenario tests (F2)."""

import time

import dst as dst_mod
from dst.scenarios import db_insert_storm
from dst.testing import Scorecard, invariants_failed, replay_check


def run_scorecard(**kwargs) -> Scorecard:
    result = dst_mod.run(db_insert_storm.main(**kwargs))
    assert result.done, f"scenario failed: {result.error}"
    assert result.error is None
    return result.value


def test_small_run_invariants_dups_and_faults():
    card = run_scorecard(total=50_000, dup_pct=5, deadlock_pct=2, seed=42)

    assert invariants_failed(card) == []
    assert card.counters["inserted"] + card.counters["skipped_dups"] == 50_000
    assert card.counters["dup_rejected"] > 0
    assert card.counters["faults_raised_total"] > 0
    assert card.counters["retries"] >= card.counters["faults_raised_total"]
    assert card.subscores.loss == 1.0
    assert card.subscores.keep_up == 1.0
    assert card.subscores.drain == 1.0
    assert card.score == 1.0


def test_small_run_replays_byte_equal():
    kwargs: dict[str, int | float] = {
        "total": 50_000,
        "dup_pct": 5,
        "deadlock_pct": 2,
        "seed": 42,
    }
    first, second = replay_check(lambda: db_insert_storm.main(**kwargs), seed_label=42)
    assert first == second


def test_one_million_run_invariants_and_wall_budget():
    start = time.perf_counter()
    card = run_scorecard(total=1_000_000, dup_pct=1, deadlock_pct=0, seed=7)
    wall_s = time.perf_counter() - start

    assert invariants_failed(card) == []
    assert card.counters["inserted"] + card.counters["skipped_dups"] == 1_000_000
    assert card.counters["faults_raised_total"] == 0
    assert card.counters["retries"] == 0
    assert card.subscores.loss == 1.0
    assert card.subscores.drain == 1.0
    assert card.score == 1.0
    assert wall_s < 50.0


def test_zero_dup_and_deadlock_produces_clean_run():
    card = run_scorecard(total=5_000, dup_pct=0, deadlock_pct=0, seed=1)

    assert invariants_failed(card) == []
    assert card.counters["inserted"] == 5_000
    assert card.counters["skipped_dups"] == 0
    assert card.counters["dup_rejected"] == 0
    assert card.score == 1.0
