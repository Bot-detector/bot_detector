import asyncio

import pytest
from bot_detector.event_queue.structs import ScrapedStruct
from pydantic import ValidationError

from development.perf.firehose.events import EventSchedule
from development.perf.firehose.fake_kafka import FakeKafkaConsumer
from development.perf.firehose.payloads import PayloadConfig


def _make_consumer(
    error_pct: float = 0.0, poison_pct: float = 0.0
) -> FakeKafkaConsumer:
    return FakeKafkaConsumer(
        topic="players.scraped",
        group="sim",
        rate_s=200,
        payload_config=PayloadConfig(seed=1, pool_size=5),
        events=EventSchedule(seed=1, error_pct=error_pct, poison_pct=poison_pct),
    )


@pytest.mark.asyncio
async def test_get_one_full_error_pct_returns_runtime_error():
    consumer = _make_consumer(error_pct=100.0)

    result = await consumer.get_one()

    assert isinstance(result, RuntimeError)
    assert consumer.errors_returned == 1


@pytest.mark.asyncio
async def test_get_one_full_poison_pct_returns_validation_error():
    consumer = _make_consumer(poison_pct=100.0)

    result = await consumer.get_one()

    assert isinstance(result, ValidationError)
    assert consumer.poison_returned == 1


@pytest.mark.asyncio
async def test_get_one_without_events_returns_validated_message():
    consumer = _make_consumer()
    consumer._queue.put_nowait(consumer._pool[0])

    result = await consumer.get_one()

    assert isinstance(result, ScrapedStruct)
    assert result.player_data.id == 0


@pytest.mark.asyncio
async def test_get_one_error_stream_replays_with_seed():
    # pcts sum to 100: every draw injects, so get_one never blocks on
    # the empty queue
    a = _make_consumer(error_pct=60.0, poison_pct=40.0)
    b = _make_consumer(error_pct=60.0, poison_pct=40.0)

    results_a = [await a.get_one() for _ in range(40)]
    results_b = [await b.get_one() for _ in range(40)]

    kinds_a = [type(r).__name__ for r in results_a]
    kinds_b = [type(r).__name__ for r in results_b]
    assert kinds_a == kinds_b
    assert a.errors_returned == b.errors_returned


@pytest.mark.asyncio
async def test_producer_revives_after_stop_start_cycle():
    """The sim server keeps one consumer per group; a queue delete
    (last client gone) cancels its producer. A reconnect must feed
    again - guards the 'second fleet starves' failure mode."""
    consumer = _make_consumer()

    await consumer.start()
    await asyncio.sleep(0.1)
    first = consumer.produced_total
    assert first > 0

    await consumer.stop()
    await consumer.start()
    await asyncio.sleep(0.1)

    assert consumer.produced_total > first
    assert consumer._task is not None
    assert not consumer._task.done()
    await consumer.stop()
