"""reports.to_insert scenario: 2h delay, silence, then a lagged stream."""

import pytest

import dst as dst_mod
from dst.scenarios import reports_delay

TS_BASE = 2_000_000_000

SCALED = {
    "duration_s": 864,
    "feed_rate_s": 10,
    "delay_s": 72,
    "jitter_max_s": 3,
    "ts_base_s": TS_BASE,
    "client_buffer": 5000,
}


def run(**overrides) -> reports_delay.ReportsDelayReport:
    result = dst_mod.run(reports_delay.main(**{**SCALED, **overrides}), start_s=TS_BASE)
    assert result.done, f"scenario failed: {result.error}"
    assert result.error is None
    return result.value


def test_silence_holds_until_the_delay_elapses():
    report = run()

    assert report.first_received_s is not None
    first_relative = report.first_received_s - TS_BASE
    assert first_relative >= report.expected_lag_s  # delay - jitter_max
    assert first_relative < report.config.delay_s  # jitter reaches before the edge


def test_stream_lags_and_leaves_the_delay_unstreamed():
    report = run()

    # every produced message is delivered, broker-held, or in flight
    # (the pump holds the next emission-due message at cutoff)
    assert report.received + report.broker_backlog >= report.produced - 5
    # the backlog is the delay window: ~delay x rate arrivals not yet emitted
    expected_backlog = report.config.delay_s * report.config.feed_rate_s
    assert report.broker_backlog == pytest.approx(expected_backlog, rel=0.05)
    # the stream only reached duration - delay: the "2h left" at full scale
    assert report.unstreamed_s == pytest.approx(report.config.delay_s, abs=3)
    assert report.unstreamed_hours == pytest.approx(
        report.config.delay_s / 3600.0, abs=3 / 3600
    )


def test_ts_are_never_in_the_future_or_sequential():
    report = run()

    assert report.first_ts_offset_s is not None
    assert report.last_ts_offset_s is not None
    assert report.last_ts_offset_s > report.first_ts_offset_s
    # the stream trails the window end by roughly the delay
    assert (
        report.last_ts_offset_s < report.config.duration_s - report.config.delay_s + 3
    )


def test_scenario_replays_identically():
    assert run() == run()


def test_topic_holds_restored_after_run():
    from bot_detector.firehose.app import queue_manager

    run()
    adapter = queue_manager.TOPIC_HOLDS.get("reports.to_insert")
    assert adapter is not None
    assert adapter.delay_s == 7200  # product default, not the scaled 72


def test_invalid_config_rejected():
    import asyncio

    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        asyncio.run(reports_delay.main(duration_s=0))
    with pytest.raises(ValidationError):
        asyncio.run(reports_delay.main(jitter_max_s=-1))
