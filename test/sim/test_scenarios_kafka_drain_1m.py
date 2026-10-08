"""kafka_drain_1m scenario: feed/drain parity on the virtual clock."""

import time

import dst as dst_mod
from dst.scenarios import kafka_drain_1m as scenario
from dst.testing import (
    Scorecard,
    invariants_failed,
    replay_check,
    report_bytes,
)


def run(**kwargs) -> Scorecard:
    result = dst_mod.run(scenario.main(**kwargs))
    assert result.done, f"scenario failed: {result.error}"
    assert result.error is None
    return result.value


def test_small_run_clean_and_fast():
    t0 = time.perf_counter()
    card = run(total=50_000, rate_s=500_000, batch=10_000)
    wall = time.perf_counter() - t0

    assert wall < 5.0
    assert invariants_failed(card) == []
    assert card.counters["produced"] == 50_000
    assert card.counters["consumed"] == 50_000
    assert card.counters["faulted_produce"] == 0
    assert card.counters["faulted_fetch"] == 0


def test_fast_consumer_scores_full():
    card = run(total=50_000, rate_s=100_000, batch=10_000)

    assert card.subscores.keep_up == 1.0
    assert card.subscores.drain == 1.0
    assert card.subscores.loss == 1.0
    assert card.score == 1.0


def test_slow_consumer_degrades_keep_up_but_keeps_loss_clean():
    card = run(
        total=50_000,
        rate_s=100_000,
        batch=10_000,
        consumer_batch=5_000,
        consumer_sleep_s=0.05,
    )

    assert 0.0 < card.subscores.keep_up < 1.0
    assert card.subscores.loss == 1.0
    assert card.counters["consumed"] == card.counters["produced"] == 50_000
    assert "no_loss" not in invariants_failed(card)
    assert "offsets_monotonic" not in invariants_failed(card)


def test_scenario_replays_byte_identical():
    first, second = replay_check(
        lambda: scenario.main(total=20_000, rate_s=200_000, batch=5_000),
    )
    assert first == second
    assert report_bytes(run(total=20_000, rate_s=200_000, batch=5_000)) == first


def test_one_million_drain():
    t0 = time.perf_counter()
    card = run()
    wall = time.perf_counter() - t0

    assert wall < 30.0
    assert invariants_failed(card) == []
    assert card.counters["produced"] == 1_000_000
    assert card.counters["consumed"] == 1_000_000
    assert card.counters["faulted_produce"] == 0
    assert card.counters["faulted_fetch"] == 0
