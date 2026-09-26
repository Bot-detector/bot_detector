import time

import pytest
from bot_detector.event_queue.structs import ReportsToInsertStruct
from bot_detector.firehose.app.group_stream.adapter import (
    FUTURE_LIMIT_S,
    DelayAdapter,
    message_ts,
)
from bot_detector.structs.reports import ParsedDetection


def make_report(ts: int) -> ReportsToInsertStruct:
    return ReportsToInsertStruct(
        metadata={"version": 1, "source": "test"},
        report=ParsedDetection(
            region_id=0,
            x_coord=0,
            y_coord=0,
            z_coord=0,
            ts=ts,
            equipment={},
            reporter_id=1,
            reported_id=2,
        ),
    )


@pytest.mark.asyncio
async def test_hold_passes_through_without_delay():
    adapter = DelayAdapter(delay_s=0.0)
    fresh = make_report(ts=int(time.time()) + 60)

    assert await adapter.hold(message=fresh) is True


@pytest.mark.asyncio
async def test_hold_emits_old_message_immediately():
    adapter = DelayAdapter(delay_s=2 * 60 * 60)
    old = make_report(ts=int(time.time()) - 3 * 60 * 60)

    assert await adapter.hold(message=old) is True


@pytest.mark.asyncio
async def test_hold_sleeps_for_fresh_message():
    delay_s = 2 * 60 * 60
    adapter = DelayAdapter(delay_s=delay_s)
    # eligible 5s from now
    ts = int(time.time()) - delay_s + 5
    message = make_report(ts=ts)

    start = time.monotonic()
    assert await adapter.hold(message=message) is True
    elapsed = time.monotonic() - start

    assert 4 <= elapsed <= 6


@pytest.mark.asyncio
async def test_hold_drops_message_without_ts():
    adapter = DelayAdapter(delay_s=60.0)
    message = ReportsToInsertStruct.model_construct(metadata=None, report=None)

    assert await adapter.hold(message=message) is False


@pytest.mark.asyncio
async def test_hold_emits_future_message_within_limit_immediately():
    adapter = DelayAdapter(delay_s=2 * 60 * 60)
    message = make_report(ts=int(time.time()) + 60)

    start = time.monotonic()
    assert await adapter.hold(message=message) is True
    elapsed = time.monotonic() - start

    assert elapsed < 1


@pytest.mark.asyncio
async def test_hold_drops_message_with_far_future_ts():
    adapter = DelayAdapter(delay_s=60.0)
    message = make_report(ts=int(time.time()) + int(FUTURE_LIMIT_S) + 3600)

    assert await adapter.hold(message=message) is False


@pytest.mark.asyncio
async def test_hold_passes_exceptions_through():
    adapter = DelayAdapter(delay_s=60.0)

    assert await adapter.hold(message=RuntimeError("kafka down")) is True


def test_message_ts_validates_type():
    assert message_ts(make_report(ts=123)) == 123.0
    negative = ReportsToInsertStruct.model_construct(
        report=ParsedDetection.model_construct(ts=-1)
    )
    assert message_ts(negative) is None
    broken = ReportsToInsertStruct.model_construct(report=None)
    assert message_ts(broken) is None
