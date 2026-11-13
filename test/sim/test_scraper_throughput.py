import math

import pytest

import dst as dst_mod
from dst.scenarios import scraper_throughput as scenario

_CACHE: dict[tuple, scenario.ScraperThroughputReport] = {}


def run(**kwargs) -> scenario.ScraperThroughputReport:
    """Run (or reuse) one scenario run keyed by its exact arguments."""
    key = tuple(sorted(kwargs.items()))
    if key not in _CACHE:
        result = dst_mod.run(scenario.main(**kwargs))
        assert result.done, f"scenario failed: {result.error}"
        assert result.error is None
        assert result.pending_tasks == [], result.pending_tasks
        _CACHE[key] = result.value
    return _CACHE[key]


def test_scenario_replays_byte_identical():
    # RetryTracker jitters backoff from the process RNG; the scenario
    # seeds it per run, so two runs of one seed must match byte-for-byte
    kwargs = {"duration_s": 20.0, "fetchers": 60, "processors": 4, "proxies": 12}
    reports = []
    for _ in range(2):
        result = dst_mod.run(scenario.main(**kwargs))
        assert result.done, f"scenario failed: {result.error}"
        assert result.error is None
        reports.append(result.value.model_dump_json())
    assert reports[0] == reports[1]


# panel-calibrated per-outcome lognormal means (Nov 2026 Grafana panel
# hiscore_scraper_fetch_latency): mean = p50 * exp(sigma^2 / 2), with
# sigma = ln(p99/p50) / z99 and the config's p50/p99 anchors
_Z99 = 2.3263478740408408
_MEAN_SUCCESS_S = 1.45 * math.exp((math.log(4.2) / _Z99) ** 2 / 2)
_MEAN_NF_S = 1.45 * math.exp((math.log(3.1) / _Z99) ** 2 / 2)
_MEAN_ERROR_S = 0.33 * math.exp((math.log(6.7) / _Z99) ** 2 / 2)
# crawl mix (the defaults): 54.5% not_found, 2% errors, 43.5% success
_CRAWL_MEAN_S = 0.545 * _MEAN_NF_S + 0.02 * _MEAN_ERROR_S + 0.435 * _MEAN_SUCCESS_S
# sprint mix (not_found_pct=0): 98% success, 2% errors
_SPRINT_MEAN_S = 0.98 * _MEAN_SUCCESS_S + 0.02 * _MEAN_ERROR_S


def test_batched_commit_takes_commit_rtt_off_the_critical_path():
    card = run()  # crawl mix, 5ms commit RTT
    print(card.summary())

    # one commit per 200-player batch: consumer cap ~40,000/s, orders
    # of magnitude above the pool
    assert card.binding == "fleet"
    assert card.consumer_cap_s == pytest.approx(
        card.config.consume_batch_size / card.config.commit_cost_s, rel=0.01
    )
    assert card.consumer_cap_s > 20 * card.fleet_cap_s

    # commits track batches, not players (a startup transient yields
    # some short batches while the pool warms up, so assert the
    # amortization bound rather than exact batch sizes)
    assert card.commits < 0.3 * card.consumed
    assert card.stages["commit"].share_pct < 1.0

    # the pool binds on fetch latency: ~1080/s, the panel-calibrated
    # success tail carrying the pool mean
    assert card.throughput_s == pytest.approx(card.fleet_cap_s, rel=0.10)
    assert card.throughput_s == pytest.approx(card.fetchers / _CRAWL_MEAN_S, rel=0.15)


def test_consistency_counts():
    card = run()  # same cached default run (crawl mix)

    # every consumed record is scraped, not_found or an error. At the
    # cut, names sit between consume and fetch outcome: task_queue,
    # results_queue and one in-flight fetch per fetcher
    outcomes = card.outcomes.scraped + card.outcomes.not_found + card.outcomes.errors
    in_flight_bound = (
        card.config.task_queue_maxsize
        + card.config.results_queue_maxsize
        + card.fetchers
    )
    assert outcomes >= card.consumed - in_flight_bound

    # outputs land on their topics
    assert card.scraped_produced == pytest.approx(card.outcomes.scraped, rel=0.01)
    assert card.not_found_produced == pytest.approx(card.outcomes.not_found, rel=0.01)

    # outcome mix matches prod: ~20% more not_found than found
    # (share = 1.2 / 2.2 ~ 0.545)
    nf_share = card.outcomes.not_found / (
        card.outcomes.not_found + card.outcomes.scraped
    )
    assert nf_share == pytest.approx(1.2 / 2.2, abs=0.02)

    # requeued transient errors re-enter the topic: backlog stays
    # bounded because consumption outpaces requeues
    assert card.backlog < card.feed_produced


def test_fetch_latency_distribution_matches_prod_calibration():
    card = run()  # same cached default run
    nf = card.latency["not_found"]
    success = card.latency["success"]
    error = card.latency["error"]
    assert nf.calls > 0 and success.calls > 0 and error.calls > 0

    # prod panel anchors (Nov 2026): per-outcome lognormal p50/p99
    assert nf.p50_s == pytest.approx(1.45, rel=0.10)
    assert nf.p99_s == pytest.approx(4.5, rel=0.15)
    assert nf.mean_s == pytest.approx(_MEAN_NF_S, rel=0.10)

    # success carries the fattest tail: p99 ~6.1s vs ~4.5s
    assert success.p50_s == pytest.approx(1.45, rel=0.10)
    assert success.p99_s == pytest.approx(1.45 * 4.2, rel=0.15)
    assert success.p99_s > nf.p99_s
    assert success.mean_s == pytest.approx(_MEAN_SUCCESS_S, rel=0.10)

    # failures are fast: p50 ~0.33s, p99 ~2.2s. The default 120s run is
    # episode-free (first episode lands at ~283s of virtual time on the
    # seeded schedule), so no draw hits the 30s client timeout
    assert error.p50_s == pytest.approx(0.33, rel=0.10)
    assert error.p99_s == pytest.approx(2.2, rel=0.20)
    assert card.outcomes.timeouts == 0
    assert card.degradation_episodes == 0


def test_partitions_stay_balanced():
    card = run()  # same cached default run
    mean_p = sum(card.per_partition_consumed) / card.partitions
    spread = max(card.per_partition_consumed) - min(card.per_partition_consumed)
    assert spread < 0.05 * mean_p
    # partition counters tick when a message is fetched, consumed when
    # a name is parsed: at most one in-flight consume batch of names at
    # the cut (plus requeue singletons)
    assert (
        abs(sum(card.per_partition_consumed) - card.consumed)
        <= card.config.consume_batch_size + card.partitions
    )


def test_rate_limit_caps_the_pool_when_proxies_are_scarce():
    card = run(duration_s=120.0, proxies=8, not_found_pct=0.0)
    print(card.summary())

    # 1800 fetchers over 8 proxies demand ~1800/s, but each proxy's
    # shared window binds: throughput pins to the nominal
    # 8 x 20 = 160/s cap from below
    assert card.binding == "rate"
    assert card.rate_cap_s == pytest.approx(160.0)
    assert card.throughput_s == pytest.approx(160.0, rel=0.05)

    # fetcher slots pile up inside the limiter's check()
    assert card.stages["rate_limit"].share_pct > 30.0


def test_single_connection_no_longer_serializes_the_pipeline():
    card = run(
        duration_s=120.0,
        not_found_pct=0.0,
        kafka_connection_limit=1,
    )
    print(card.summary())

    # with per-batch commits the serial path is ~7ms per 200 players
    # even on one broker connection, so the pool binds: the
    # success-heavy mix caps at fetchers / its panel-calibrated mean
    assert card.binding == "fleet"
    assert card.throughput_s == pytest.approx(card.fetchers / _SPRINT_MEAN_S, rel=0.15)


def test_outcome_mix_is_neutral_for_the_pool_cap():
    crawl = run(
        duration_s=120.0,
        commit_cost_s=0.0005,
        fetch_cost_s=0.001,
        not_found_pct=54.5,
    )
    sprint = run(
        duration_s=120.0,
        commit_cost_s=0.0005,
        fetch_cost_s=0.001,
        not_found_pct=0.0,
    )
    print(crawl.summary())

    # cheap broker so only the pool binds. Under the panel calibration
    # the mix barely moves the cap: the success tail (p99 ~6.1s)
    # outweighs the not_found tail (p99 ~4.5s) while errors are fast
    # failures (p50 0.33s), so crawl ~1080/s vs sprint ~1040/s
    assert sprint.binding == "fleet"
    assert crawl.binding == "fleet"
    assert sprint.throughput_s == pytest.approx(
        sprint.fetchers / _SPRINT_MEAN_S, rel=0.10
    )
    assert crawl.throughput_s == pytest.approx(crawl.fetchers / _CRAWL_MEAN_S, rel=0.10)
    ratio = sprint.throughput_s / crawl.throughput_s
    assert 0.85 < ratio < 1.05


def test_dropping_null_fields_shrinks_messages_not_throughput():
    full = run(
        duration_s=90.0,
        not_found_pct=0.0,
        commit_cost_s=0.0005,
        fetch_cost_s=0.001,
    )
    slim = run(
        duration_s=90.0,
        not_found_pct=0.0,
        commit_cost_s=0.0005,
        fetch_cost_s=0.001,
        exclude_none_fields=True,
    )
    print(
        f"avg name bytes: full={full.avg_name_bytes:.0f}B "
        f"slim={slim.avg_name_bytes:.0f}B "
        f"({100 * (1 - slim.avg_name_bytes / full.avg_name_bytes):.1f}% smaller)"
    )

    # dropping the 4 null fields (ironman/hardcore_ironman/
    # ultimate_ironman/normalized_name) trims ~30% of message bytes
    assert slim.avg_name_bytes < full.avg_name_bytes
    assert 0.60 < slim.avg_name_bytes / full.avg_name_bytes < 0.95
    assert full.bytes_transferred > 0 and slim.bytes_transferred > 0

    # at a 100 MB/s link (800 Mbps default) the ~100B saving is
    # microseconds per message: throughput stays pool-bound and equal
    assert full.binding == "fleet" and slim.binding == "fleet"
    assert slim.throughput_s == pytest.approx(full.throughput_s, rel=0.10)
    assert full.kafka_fetch_failures == 0 and slim.kafka_fetch_failures == 0


def test_starved_feed_paces_the_pipeline():
    card = run(
        duration_s=90.0,
        feed_rate_s=100,
    )
    print(card.summary())

    # 100/s is below every cap: consumption tracks the feed exactly
    assert card.binding == "feed"
    assert card.throughput_s == pytest.approx(100.0, rel=0.15)

    # the pool outruns the feed, so the consumer's get_many wait is
    # mostly blocked time on the delivery queue
    get = card.stages["kafka_get"]
    assert get.blocked_s > 0.5 * get.total_s
    assert card.backlog < 0.1 * card.feed_produced
