"""Sim validation for the scrape-rate drop signature.

With per-outcome fetch latencies (successes fast, not-founds slow), a
worker fleet reproduces the observed production signature: ~450/s in
success-heavy segments (normal step) vs ~200/s in not_found-heavy
segments (possible_ban step), with no change in worker count or
success latency.
"""

import asyncio

import dst as dst_mod
import pytest

WORKERS = 450
WINDOW_S = 600.0
SUCCESS_LATENCY_S = 1.0
NOT_FOUND_LATENCY_S = 3.0

# crawl mix (possible_ban step): 3 of every 5 iterations are not_found
CRAWL_NOT_FOUND_MOD = 5
CRAWL_NOT_FOUND_HIT = 3


async def _worker(
    deadline_s: float, not_found_mod: int | None, counts: list[int]
) -> None:
    loop = asyncio.get_running_loop()
    iterations = 0
    while loop.time() < deadline_s:
        is_not_found = (
            not_found_mod is not None
            and iterations % not_found_mod < CRAWL_NOT_FOUND_HIT
        )
        latency = NOT_FOUND_LATENCY_S if is_not_found else SUCCESS_LATENCY_S
        await asyncio.sleep(latency)
        counts[0] += 1
        counts[1] += is_not_found
        iterations += 1


async def _fleet(not_found_mod: int | None) -> tuple[int, int]:
    counts = [0, 0]
    await asyncio.gather(
        *[_worker(WINDOW_S, not_found_mod, counts) for _ in range(WORKERS)]
    )
    return counts[0], counts[1]


def _expected_rate(not_found_share: float) -> float:
    mean_latency = (
        not_found_share * NOT_FOUND_LATENCY_S
        + (1 - not_found_share) * SUCCESS_LATENCY_S
    )
    return WORKERS / mean_latency


def test_not_found_heavy_mix_halves_the_fleet_rate():
    result = dst_mod.run(_fleet(CRAWL_NOT_FOUND_MOD))
    assert result.done
    assert result.error is None
    total, not_found = result.value

    share = not_found / total
    assert share == pytest.approx(CRAWL_NOT_FOUND_HIT / CRAWL_NOT_FOUND_MOD, abs=0.01)

    rate = total / WINDOW_S
    assert rate == pytest.approx(_expected_rate(share), rel=0.05)
    # the production signature: sprint ~450/s vs crawl ~200/s
    assert rate == pytest.approx(200.0, abs=25.0)


def test_success_heavy_mix_keeps_the_full_fleet_rate():
    result = dst_mod.run(_fleet(None))
    assert result.done
    assert result.error is None
    total, not_found = result.value
    assert not_found == 0

    rate = total / WINDOW_S
    assert rate == pytest.approx(_expected_rate(0.0), rel=0.05)  # ~450/s
