import time

import dst as dst_mod
from dst.scenarios import kafka_poison_advance as scenario
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


def test_poison_pages_advance_and_keep_valid():
    t0 = time.perf_counter()
    card = run(pages=20, page_size=40, batch=25)
    wall = time.perf_counter() - t0

    assert wall < 5.0
    assert invariants_failed(card) == []
    assert card.counters["consumed"] == card.counters["valid_total"]
    assert card.counters["skipped"] == card.counters["expected_poison"]
    assert card.counters["error_results"] == 0
    # one get_many call per page: proof the loop advanced, not spun
    assert card.counters["get_many_calls"] == 20


def test_scores_full_on_clean_run():
    card = run(pages=10, page_size=40, batch=25)

    assert card.subscores.loss == 1.0
    assert card.subscores.keep_up == 1.0
    assert card.subscores.drain == 1.0
    assert card.score == 1.0


def test_scenario_replays_byte_identical():
    first, second = replay_check(lambda: scenario.main(pages=10, page_size=40))
    assert first == second
    assert report_bytes(run(pages=10, page_size=40)) == first


def test_scenario_registered_in_naming_gate():
    # guard against silent module drift: the naming gate pins disk == expected
    import test.sim.test_scenario_naming as naming

    assert "kafka_poison_advance" in naming.EXPECTED_MODULES
