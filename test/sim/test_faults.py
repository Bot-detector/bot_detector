"""dst.faults: counter-based draw determinism and independence."""

import pytest
from pydantic import ValidationError

import dst


def test_draw_is_deterministic():
    assert dst.draw(7, "k:p:topic:0", 0) == dst.draw(7, "k:p:topic:0", 0)
    assert dst.draw(7, "k:p:topic:0", 1) == dst.draw(7, "k:p:topic:0", 1)


def test_draw_matches_pinned_vector():
    # blake2b(digest_size=8) over "0:k:p:topic:0:0"
    assert dst.draw(0, "k:p:topic:0", 0) == 0.819882606613206


def test_draw_order_independence():
    stream = "db:x:report"
    forward = [dst.draw(42, stream, i) for i in range(100)]
    backward = [dst.draw(42, stream, i) for i in reversed(range(100))]
    assert forward == list(reversed(backward))


def test_draw_shard_independence():
    # Shards interleave draws in arbitrary order; per-op outcomes match.
    ops = [(5, "k:c:group:0", i) for i in range(50)]
    shard_a = [dst.draw(*op) for op in ops]
    interleave = [dst.draw(*op) for op in reversed(ops[::2])] + [
        dst.draw(*op) for op in ops[1::2]
    ]
    assert sorted(shard_a) == sorted(interleave)
    for op in ops:
        assert dst.draw(*op) == dst.draw(*op)


def test_draw_distinct_inputs_differ():
    values = (
        {dst.draw(1, "k:p:t:0", i) for i in range(1000)}
        | {dst.draw(1, "k:p:t:1", i) for i in range(1000)}
        | {dst.draw(2, "k:p:t:0", i) for i in range(1000)}
    )
    assert len(values) == 3000


def test_draw_in_unit_interval():
    draws = [dst.draw(9, "db:pool", i) for i in range(10_000)]
    assert all(0.0 <= d < 1.0 for d in draws)


def test_draw_covers_unit_interval_uniformly():
    draws = [dst.draw(11, "db:x:player", i) for i in range(10_000)]
    bins = 10
    counts = [0] * bins
    for d in draws:
        counts[min(int(d * bins), bins - 1)] += 1
    expected = len(draws) / bins
    tolerance = 3 * (expected * (1 - 1 / bins)) ** 0.5
    for count in counts:
        assert abs(count - expected) < tolerance


def test_bucket_resolves_cumulative_order():
    assert dst.bucket(0.0, 10.0, 20.0) == 0
    assert dst.bucket(0.099, 10.0, 20.0) == 0
    assert dst.bucket(0.10, 10.0, 20.0) == 1
    assert dst.bucket(0.299, 10.0, 20.0) == 1
    assert dst.bucket(0.30, 10.0, 20.0) == -1
    assert dst.bucket(0.999, 0.0, 0.0) == -1


def test_kafka_fault_config_defaults_are_off():
    faults = dst.KafkaFaultConfig()
    assert faults.produce_buffer_timeout_pct == 0.0
    assert faults.commit_fail_pct == 0.0
    assert faults.outage_pct == 0.0


def test_kafka_fault_config_group_budgets():
    dst.KafkaFaultConfig(
        produce_buffer_timeout_pct=60.0,
        produce_closed_pct=40.0,
        fetch_timeout_pct=25.0,
        consumer_stopped_pct=25.0,
        poison_pct=25.0,
        slow_fetch_pct=25.0,
        commit_fail_pct=50.0,
        commit_timeout_pct=50.0,
    )
    with pytest.raises(ValidationError, match="produce"):
        dst.KafkaFaultConfig(
            produce_buffer_timeout_pct=60.0,
            produce_closed_pct=41.0,
        )
    with pytest.raises(ValidationError, match="fetch"):
        dst.KafkaFaultConfig(poison_pct=40.0, slow_fetch_pct=70.0)
    with pytest.raises(ValidationError, match="commit"):
        dst.KafkaFaultConfig(commit_fail_pct=51.0, commit_timeout_pct=50.0)


def test_fault_config_unknown_knob_rejects():
    with pytest.raises(ValidationError, match="nope_pct"):
        dst.KafkaFaultConfig(**{"nope_pct": 1.0})
    with pytest.raises(ValidationError, match="nope_pct"):
        dst.DbFaultConfig(**{"nope_pct": 1.0})
    with pytest.raises(ValidationError, match="nope_pct"):
        dst.JagexFaultConfig(**{"nope_pct": 1.0})
    with pytest.raises(ValidationError, match="nope"):
        dst.FaultConfig(**{"nope": 1})


def test_db_fault_config_statement_budget():
    dst.DbFaultConfig(
        deadlock_pct=20.0,
        lock_wait_timeout_pct=20.0,
        conn_lost_pct=20.0,
        too_many_conn_pct=20.0,
        temp_table_full_pct=10.0,
        dup_key_pct=10.0,
        pool_timeout_pct=90.0,
    )
    with pytest.raises(ValidationError, match="statement"):
        dst.DbFaultConfig(deadlock_pct=60.0, lock_wait_timeout_pct=60.0)
    with pytest.raises(ValidationError, match="statement"):
        dst.DbFaultConfig(
            deadlock_pct=50.0,
            lock_wait_timeout_pct=51.0,
        )


def test_jagex_fault_config_request_budget():
    dst.JagexFaultConfig(redirect_pct=50.0, server_error_pct=50.0, proxy_ban_pct=100.0)
    with pytest.raises(ValidationError, match="request"):
        dst.JagexFaultConfig(redirect_pct=50.0, server_error_pct=50.1)


def test_fault_config_nests_per_system():
    config = dst.FaultConfig(
        kafka=dst.KafkaFaultConfig(commit_fail_pct=5.0),
        db=dst.DbFaultConfig(deadlock_pct=1.0),
        jagex=dst.JagexFaultConfig(redirect_pct=2.0),
    )
    assert config.kafka.commit_fail_pct == 5.0
    assert config.db.deadlock_pct == 1.0
    assert config.jagex.redirect_pct == 2.0
    with pytest.raises(ValidationError):
        config.kafka.commit_fail_pct = 6.0
