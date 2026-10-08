"""Firehose-on-DST scenario: parity, determinism, kick path, faults."""

import asyncio

import pytest
from pydantic import ValidationError

import dst as dst
import dst.scenarios.firehose as fh


def run(**kwargs) -> fh.FirehoseReport:
    result = dst.run(fh.main(**kwargs))
    assert result.done, f"scenario failed: {result.error}"
    assert result.error is None
    return result.value


def test_happy_path_parity_and_clean_state():
    report = run(
        duration_s=5, feed_rate_s=200, pool_size=100, n_clients=3, kick_grace_s=30.0
    )

    received = [c.received for c in report.clients]
    assert all(c.received > 0 for c in report.clients)
    assert max(received) - min(received) <= 2  # parity within a few messages
    assert report.kicked == 0
    assert report.dropped == 0
    assert report.backlog < 200 * 5  # near-live consumption
    assert report.connections_left == 0
    assert all(c.close_code == 1000 for c in report.clients)
    assert report.messages_delivered == sum(c.received for c in report.clients)


def test_scenario_replays_identically():
    kwargs = {
        "duration_s": 5,
        "feed_rate_s": 200,
        "pool_size": 100,
        "n_clients": 3,
        "error_pct": 1.0,
        "poison_pct": 1.0,
    }
    first = run(**kwargs)
    second = run(**kwargs)
    assert first == second


def test_slow_client_gets_kicked_others_are_fine():
    report = run(
        duration_s=40,
        feed_rate_s=200,
        pool_size=100,
        n_clients=3,
        n_slow_clients=1,
        kick_grace_s=5.0,
        # client-0 drains at 20/s vs a 200/s feed: its inbox overflows
        # just past the 5s join grace -> kicked (multi-subscriber)
        client_slow_s=0.05,
    )

    slow = report.clients[0]
    fast = report.clients[1:]
    assert slow.close_code == 1013
    assert slow.received < report.produced / 3  # fell far behind
    assert report.kicked == 1
    # virtual-time determinism: the inbox fills just past the 5s grace,
    # so the first full send kicks - no grace-drop phase at this rate
    assert report.dropped == 0
    assert all(c.close_code == 1000 for c in fast)
    received_fast = [c.received for c in fast]
    assert max(received_fast) - min(received_fast) <= 2  # fast stay in parity


def test_fault_stream_runs_the_pump_backoff_path():
    report = run(
        duration_s=10,
        feed_rate_s=200,
        pool_size=100,
        n_clients=2,
        error_pct=5.0,
        poison_pct=5.0,
    )

    assert report.messages_delivered > 0  # faults never stop the pump
    assert report.kicked == 0  # errors are pump concerns, not client kicks
    # pump draws include faults; every real message goes to both clients
    assert report.messages_delivered > report.consumed


def test_repeated_runs_do_not_leak_connections():
    for _ in range(2):
        report = run(duration_s=3, feed_rate_s=100, pool_size=50, n_clients=2)
        assert report.connections_left == 0
        assert all(c.close_code == 1000 for c in report.clients)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"feed_rate_s": 0},
        {"n_clients": 0},
        {"duration_s": -1},
        {"error_pct": 101},
    ],
)
def test_invalid_config_rejected(kwargs):
    with pytest.raises(ValidationError):
        asyncio.run(fh.main(**kwargs))


def test_broker_outage_pauses_the_pump_then_recovers():
    # a cpu-capped pump (1000/s) under a faster feed (2000/s) cannot
    # drain the outage backlog within the window, so the deficit shows
    common = {
        "duration_s": 20,
        "feed_rate_s": 2000,
        "pool_size": 100,
        "n_clients": 2,
        "parse_cost_s": 0.001,
    }
    baseline = run(**common)
    outage = run(**common, outage_at_s=5, outage_duration_s=8)

    # the pump backoffs through the outage: fewer deliveries than the
    # clean run, but it recovers and keeps streaming after it
    assert outage.messages_delivered < baseline.messages_delivered
    assert outage.messages_delivered > 0
    assert outage.kicked == 0  # an outage is a pump concern, not a kick


def test_broker_outage_replays_identically():
    kwargs = {
        "duration_s": 20,
        "feed_rate_s": 200,
        "pool_size": 100,
        "n_clients": 2,
        "outage_at_s": 5,
        "outage_duration_s": 8,
    }
    assert run(**kwargs) == run(**kwargs)
