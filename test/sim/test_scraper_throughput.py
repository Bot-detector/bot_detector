"""Throughput sim: the real hiscore scraper pipeline on a simulated kafka.

Runs the unmodified stage functions (batched consumer, 1800-fetcher
pool over 250 proxies with per-proxy rate windows, 16 processors)
against a 4-partition simulated broker and a simulated Jagex API,
then answers "where is the pipeline slow" with four caps:

- the consumer serial path: one commit RTT per `consume_batch_size`
  players (the old per-message commit used to cap the fleet at
  1/commit_rtt);
- the fetch pool: Little's law, fetchers / mean fetch latency;
- the per-proxy rate ceilings: proxies x 20 req/s;
- the feed rate itself.

Expectations encoded here (computed in the report, asserted within
tolerance):

- the batched commit leaves the consumer cap orders of magnitude above
  the pool, so the crawl-mix pool binds on fetch latency: ~1250/s
  (1800 fetchers / 250 proxies) vs the ~450-worker fleet's ~300/s,
  with a cheap commit path;
- scarce proxies bind the pool on the shared rate windows instead
  (proxies x 20/s), proving the pool actually uses the rate budget;
- fetch latency distributions reproduce the prod calibration:
  mixture p50 ~1.7s, p99 ~5s;
- a starved feed (below every cap) paces consumption at exactly the
  feed rate.
"""

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


# crawl-mix pool mean: 54.5% not_found (lognormal median 1.7s, mean
# 1.7 * exp(sigma^2/2)) plus successes/errors at ~1s
_NF_MEAN_S = 1.7 * math.exp((math.log(2.9412) / 2.3263478740408408) ** 2 / 2)
_CRAWL_MEAN_S = 0.545 * _NF_MEAN_S + 0.455 * 1.0


def test_batched_commit_takes_commit_rtt_off_the_critical_path():
    card = run()  # crawl mix, 5ms commit RTT
    print(card.summary())

    # one commit per 200-player batch: consumer cap ~40,000/s, orders
    # of magnitude above the pool. The old per-message commit capped the
    # same shape at ~200/s.
    assert card.binding == "fleet"
    assert card.consumer_cap_s == pytest.approx(
        card.config.consume_batch_size / card.config.commit_cost_s, rel=0.01
    )
    assert card.consumer_cap_s > 20 * card.fleet_cap_s

    # commits track batches, not players: orders of magnitude fewer
    # commits than the old one-per-message pattern (a startup transient
    # yields some short batches while the pool warms up, so assert the
    # amortization bound rather than exact batch sizes)
    assert card.commits < 0.3 * card.consumed
    assert card.stages["commit"].share_pct < 1.0

    # the pool binds on fetch latency: ~715/s (was ~300/s with 450
    # per-message-commit workers, and that was against a 200/s commit cap)
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
    assert nf.calls > 0 and success.calls > 0

    # prod: overall p50 ~1.7s sits inside the not_found distribution,
    # overall p99 ~5s is its tail
    assert nf.p50_s == pytest.approx(1.7, rel=0.10)
    assert nf.p99_s == pytest.approx(5.0, rel=0.15)
    assert nf.mean_s == pytest.approx(
        1.7 * math.exp((math.log(2.9412) / 2.3263478740408408) ** 2 / 2), rel=0.10
    )

    # successes stay tight around 1s
    assert success.mean_s == pytest.approx(1.0, rel=0.05)
    assert success.p99_s < 1.3


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
    # shared window binds: with reservation-based check(), throughput
    # pins to the nominal 8 x 20 = 160/s cap from below - the old
    # check-in-time accounting leaked bursts ~20% past it
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

    # one broker connection used to serialize every per-message commit
    # behind the fetch RTTs (~143/s). With per-batch commits the serial
    # path is ~7ms per 200 players, so the pool binds instead.
    assert card.binding == "fleet"
    assert card.throughput_s == pytest.approx(card.fetchers / 1.004, rel=0.15)


def test_not_found_mix_still_stretches_the_pool():
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

    # cheap broker so only the pool binds: sprint ~1020/s vs crawl
    # ~715/s - the crawl's not_found fetches (p50 1.7s, p99 5s tail)
    # stretch the mean fetch from ~1.0s to ~1.43s
    assert sprint.binding == "fleet"
    assert crawl.binding == "fleet"
    assert sprint.throughput_s == pytest.approx(sprint.fetchers / 1.004, rel=0.10)
    assert crawl.throughput_s == pytest.approx(crawl.fetchers / _CRAWL_MEAN_S, rel=0.10)
    ratio = sprint.throughput_s / crawl.throughput_s
    assert 1.2 < ratio < 1.9


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
