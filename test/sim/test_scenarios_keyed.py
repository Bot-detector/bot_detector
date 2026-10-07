"""Keyed-client scenario: per-user groups isolated from the anonymous one."""

import asyncio

import pytest
from pydantic import ValidationError

import dst as dst_mod
from dst.scenarios import keyed


def run(**kwargs) -> keyed.KeyedIsolationReport:
    result = dst_mod.run(keyed.main(**kwargs))
    assert result.done, f"scenario failed: {result.error}"
    assert result.error is None
    return result.value


def test_keyed_clients_get_their_full_stream():
    report = run(duration_s=10, feed_rate_s=200, pool_size=50, n_keyed=2, n_anonymous=0)

    for client in report.keyed_clients:
        assert client.close_code == 1000
        assert client.received == client.sent
    # every keyed group consumed its whole feed: no drops, no kicks
    assert report.keyed_kicked == 0
    assert report.keyed_dropped == 0
    for client, (group, produced) in zip(
        report.keyed_clients,
        sorted(report.produced_per_group.items()),
        strict=True,
    ):
        assert client.name != group
        assert client.received >= produced - 2  # full stream minus the tail


def test_slow_anonymous_fleet_does_not_touch_keyed_clients():
    report = run(
        duration_s=30,
        feed_rate_s=200,
        pool_size=50,
        n_keyed=2,
        n_anonymous=3,
        anonymous_slow_s=0.02,
        anonymous_buffer=200,
        keyed_buffer=5000,
        kick_grace_s=5.0,
    )

    # keyed: clean, full streams on their own groups
    assert report.keyed_kicked == 0
    assert report.keyed_dropped == 0
    assert all(c.close_code == 1000 for c in report.keyed_clients)
    received = [c.received for c in report.keyed_clients]
    assert received[0] == received[1]  # keyed parity across users

    # anonymous: same feed, same server, degraded
    assert report.anonymous_kicked >= 1
    assert any(c.close_code == 1013 for c in report.anonymous_clients)

    # groups are independent: keyed feeds were not drained by the
    # anonymous mess
    for group, produced in report.produced_per_group.items():
        if group.startswith("fh-anonymous"):
            continue
        assert produced == pytest.approx(200 * 30, rel=0.05)


def test_scenario_replays_identically():
    kwargs = {
        "duration_s": 15,
        "feed_rate_s": 200,
        "pool_size": 50,
        "n_keyed": 2,
        "n_anonymous": 2,
        "anonymous_slow_s": 0.02,
        "anonymous_buffer": 200,
        "kick_grace_s": 5.0,
    }
    assert run(**kwargs) == run(**kwargs)


def test_invalid_config_rejected():
    with pytest.raises(ValidationError):
        asyncio.run(keyed.main(duration_s=0))
    with pytest.raises(ValidationError):
        asyncio.run(keyed.main(n_keyed=-1))
