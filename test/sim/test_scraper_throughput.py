"""Throughput sim: the real hiscore scraper fleet on a simulated kafka.

Runs the unmodified `work()` loop (450 workers, per-worker rate
windows, retry backoff) against a 4-partition simulated broker and a
simulated Jagex API, then answers "where is it slow" with two lenses:

- the consumer serial path: fetch RTT + parse CPU + commit RTT per
  message, all flowing through one shared consumer instance, caps the
  whole fleet when it binds;
- worker-time stage shares: where the fleet's hours actually go.

- expectations encoded here (computed in the report, asserted within
tolerance):

- a 5ms per-message commit RTT binds the fleet at 1/commit_rtt ~ 200
  msg/s, below both the 450-worker sprint demand (~450/s) and the
  recalibrated crawl demand (~300/s); workers pile up on the commit
  lock.
- with a cheap commit path the fleet binds instead: sprint mix
  (~1s fetches) sustains ~450/s, the not_found-heavy crawl mix
  (54.5% share, p50 1.7s) drops to ~300/s.
- fetch latency distributions reproduce the prod calibration:
  mixture p50 ~1.7s, p99 ~5s.
- a starved feed (below every cap) leaves workers blocked in get_one
  consuming at exactly the feed rate.
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


def test_commit_rtt_caps_the_fleet_when_commit_is_expensive():
    card = run(duration_s=120.0, not_found_pct=0.0)  # sprint mix, 5ms commit RTT
    print(card.summary())

    # 450 workers demand ~448/s, but every message pays a commit round
    # trip through the one shared consumer: hard cap at 1/5ms = 200/s
    assert card.binding == "consumer"
    assert card.consumer_cap_s == pytest.approx(200.0, rel=0.01)
    assert card.throughput_s == pytest.approx(card.consumer_cap_s, rel=0.12)
    assert card.consumer_cap_s < card.fleet_cap_s

    # the fleet queues up on the commit lock: most commit time is lock
    # wait, and one commit lands per consumed message (minus the
    # workers cancelled mid commit at the end of the window)
    commit = card.stages["commit"]
    assert commit.blocked_s > 0.8 * commit.total_s
    assert card.commits == pytest.approx(card.consumed, rel=0.05)


def test_consistency_counts_and_worker_time():
    card = run()  # same cached default run (crawl mix, 5ms commit RTT)

    # every consumed record is scraped, not_found or an error, and
    # commits track consumption (one per iteration; the small gap is
    # workers cancelled while queued on the commit lock, which is a
    # large fraction of each iteration when the lock is saturated)
    outcomes = card.outcomes.scraped + card.outcomes.not_found + card.outcomes.errors
    assert outcomes >= 0.99 * card.consumed
    assert card.commits >= 0.98 * card.consumed

    # worker-time reconciles against the simulated window
    assert card.busy_worker_s <= card.workers * card.duration_s
    assert card.busy_worker_s > 0.7 * card.workers * card.duration_s

    # outputs land on their topics
    assert card.scraped_produced == pytest.approx(card.outcomes.scraped, rel=0.01)
    assert card.not_found_produced == pytest.approx(card.outcomes.not_found, rel=0.01)

    # outcome mix matches prod: ~20% more not_found than found
    # (share = 1.2 / 2.2 ~ 0.545)
    nf_share = card.outcomes.not_found / (
        card.outcomes.not_found + card.outcomes.scraped
    )
    assert nf_share == pytest.approx(1.2 / 2.2, abs=0.02)


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

    # successes stay tight around 1s (keeps sprint ~450/s)
    assert success.mean_s == pytest.approx(1.0, rel=0.05)
    assert success.p99_s < 1.3


def test_partitions_stay_balanced():
    card = run()  # same cached default run
    mean_p = sum(card.per_partition_consumed) / card.partitions
    spread = max(card.per_partition_consumed) - min(card.per_partition_consumed)
    assert spread < 0.05 * mean_p
    # partition counters tick when a message is fetched, consumed when
    # a name is served: at most one in-flight name per partition at cut
    assert abs(sum(card.per_partition_consumed) - card.consumed) <= card.partitions


def test_cheap_commit_path_releases_the_fleet():
    card = run(
        duration_s=120.0,
        commit_cost_s=0.0005,
        fetch_cost_s=0.001,
        not_found_pct=0.0,
    )
    print(card.summary())

    # serial path 1.7ms -> consumer cap ~588/s; the fleet itself binds
    # at workers / mean latency ~ 450/s
    assert card.binding == "fleet"
    assert card.consumer_cap_s > card.fleet_cap_s
    assert card.throughput_s == pytest.approx(card.fleet_cap_s, rel=0.10)
    assert card.stages["kafka_get"].share_pct < 10.0


def test_not_found_mix_halves_the_fleet_rate():
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

    # recalibrated signature: sprint ~445/s vs crawl ~300/s - the
    # crawl's not_found fetches (p50 1.7s, p99 5s tail) stretch the
    # mean iteration from ~1.0s to ~1.5s
    assert sprint.binding == "fleet"
    assert crawl.binding == "fleet"
    assert sprint.throughput_s == pytest.approx(445.0, rel=0.10)
    assert crawl.throughput_s == pytest.approx(300.0, rel=0.10)
    ratio = sprint.throughput_s / crawl.throughput_s
    assert 1.2 < ratio < 1.9


def test_batched_names_lift_the_commit_cap():
    card = run(duration_s=120.0, names_per_message=10)  # crawl mix, 5ms commit RTT
    print(card.summary())

    # 10 names per kafka message -> one commit per 10 players: the
    # consumer cap moves from 10 x 200/s to 10 x 200/s = 2000/s, so the
    # fetch-bound fleet (~300/s crawl) binds instead of the commit lock
    assert card.binding == "fleet"
    assert card.throughput_s == pytest.approx(300.0, rel=0.12)
    assert card.consumer_cap_s == pytest.approx(2000.0, rel=0.01)

    # one real commit per kafka message (minus the workers cancelled
    # mid commit at the end of the window)
    assert card.commits == pytest.approx(card.messages_consumed, rel=0.05)
    # ~10 names per fetched message; late requeued singletons sit in the
    # backlog behind the flood and barely feature in the window
    assert card.messages_consumed == pytest.approx(card.consumed / 10, rel=0.05)


def test_starved_feed_leaves_workers_blocked_in_get_one():
    card = run(
        duration_s=90.0,
        feed_rate_s=100,
    )
    print(card.summary())

    # 100/s is below every cap: consumption tracks the feed exactly
    assert card.binding == "feed"
    assert card.throughput_s == pytest.approx(100.0, rel=0.15)

    # the fleet outruns the feed, so get_one time is almost all waiting
    get = card.stages["kafka_get"]
    assert get.blocked_s > 0.8 * get.total_s
    assert card.backlog < 0.1 * card.feed_produced
