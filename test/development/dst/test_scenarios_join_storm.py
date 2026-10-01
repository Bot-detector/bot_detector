"""Join-storm scenario: staggered joins, grace drops, kick waves."""

import pytest

import dst as dst_mod
from dst.scenarios import join_storm


def run(**kwargs) -> join_storm.JoinStormReport:
    result = dst_mod.run(join_storm.main(**kwargs))
    assert result.done, f"scenario failed: {result.error}"
    assert result.error is None
    return result.value


def test_clients_join_in_staggered_order():
    report = run(
        duration_s=20,
        feed_rate_s=200,
        pool_size=50,
        n_clients=3,
        join_interval_s=5.0,
        kick_grace_s=100.0,
        client_slow_s=0.0,
        client_buffer=5000,
    )

    assert [c.joined_at_s for c in report.clients] == [0.0, 5.0, 10.0]
    assert report.kicked == 0  # fast clients, huge grace: nobody kicked
    assert report.dropped == 0


def test_lone_subscriber_is_never_kicked():
    report = run(
        duration_s=15,
        feed_rate_s=1000,
        pool_size=100,
        n_clients=1,
        join_interval_s=15.0,
        kick_grace_s=1.0,
        client_slow_s=0.002,
        client_buffer=100,
    )

    assert report.clients[0].close_code == 1000  # pump protects the solo client
    assert report.kicked == 0
    assert report.clients[0].received > 0


def test_slow_fleet_takes_the_kick_wave():
    report = run(
        duration_s=45,
        feed_rate_s=1000,
        pool_size=100,
        n_clients=3,
        join_interval_s=10.0,
        kick_grace_s=5.0,
        client_slow_s=0.002,
        client_buffer=200,
    )

    kicked = [c for c in report.clients if c.close_code == 1013]
    assert report.kicked >= 2
    assert len(kicked) == report.kicked
    assert all(c.close_reason == "inbox full" for c in kicked)
    # kick victims still got real service before the kick
    assert all(c.received > 0 for c in kicked)


def test_scenario_replays_identically():
    kwargs = {
        "duration_s": 30,
        "feed_rate_s": 500,
        "pool_size": 50,
        "n_clients": 3,
        "join_interval_s": 8.0,
        "kick_grace_s": 5.0,
        "client_slow_s": 0.002,
        "client_buffer": 200,
    }
    assert run(**kwargs) == run(**kwargs)


def test_invalid_config_rejected():
    import asyncio

    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        asyncio.run(join_storm.main(duration_s=0))
    with pytest.raises(ValidationError):
        asyncio.run(join_storm.main(n_clients=0))
