from unittest.mock import AsyncMock, MagicMock

import pytest
from bot_detector.event_queue.adapters.memory import MemoryLagProbe
from bot_detector.event_queue.lag_probe import LagProbeProtocol
from bot_detector.job_backfill_banned import core


def _make_session_factory(pages: list[list[tuple[int, str]]]):
    """Build a session factory whose execute() returns paged (id, name) rows."""
    session = AsyncMock()
    results = []
    for page in pages:
        result = MagicMock()
        result.all.return_value = page
        results.append(result)
    session.execute = AsyncMock(side_effect=results)

    session_cm = AsyncMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=None)

    return MagicMock(return_value=session_cm)


def _make_producer(produced: list | None = None):
    """Build a QueueProducer mock whose put() collects events into `produced`.

    Args:
        produced: Optional list that receives every event passed to put().
            Enables clean post-hoc assertions without mock-introspection.
    """
    producer = MagicMock()
    producer.start = AsyncMock(return_value=None)
    producer.stop = AsyncMock(return_value=None)

    async def _put(events):
        if produced is not None:
            produced.extend(events)
        return None

    producer.put = AsyncMock(side_effect=_put)
    return producer


class _ScriptedLagProbe(LagProbeProtocol):
    """Returns a scripted sequence of lag values, one per loop iteration."""

    def __init__(self, values: list[int]) -> None:
        self._values = list(values)
        self.calls = 0

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def lag(self, topic: str, group_id: str) -> int:
        if self.calls >= len(self._values):
            return 0
        value = self._values[self.calls]
        self.calls += 1
        return value


@pytest.mark.asyncio
async def test_backfill_paginates_and_produces_each_player(monkeypatch):
    monkeypatch.setattr(core.asyncio, "sleep", AsyncMock(return_value=None))

    factory = _make_session_factory(
        [[(1, "alice"), (2, "bob"), (3, "carol")], []]
    )
    produced: list = []
    producer = _make_producer(produced=produced)

    published = await core.backfill(
        producer=producer,
        session_factory=factory,
        lag_probe=MemoryLagProbe(),
        lag_topic="players.banned",
        lag_group_id="ban_migration_worker",
        batch_size=10,
    )

    assert published == 3
    # One page -> one put() call carrying the whole batch
    assert producer.put.await_count == 1
    assert [e.player_id for e in produced] == [1, 2, 3]


@pytest.mark.asyncio
async def test_backfill_sets_metadata_source_and_name(monkeypatch):
    monkeypatch.setattr(core.asyncio, "sleep", AsyncMock(return_value=None))

    factory = _make_session_factory([[(1, "alice")], []])
    produced: list = []
    producer = _make_producer(produced=produced)

    await core.backfill(
        producer=producer,
        session_factory=factory,
        lag_probe=MemoryLagProbe(),
        lag_topic="players.banned",
        lag_group_id="ban_migration_worker",
        batch_size=10,
    )

    event = produced[0]
    assert event.metadata.source == "job_backfill_banned"
    assert event.metadata.version == 1
    assert event.player_id == 1
    assert event.name == "alice"


@pytest.mark.asyncio
async def test_backfill_terminates_when_no_banned_players(monkeypatch):
    monkeypatch.setattr(core.asyncio, "sleep", AsyncMock(return_value=None))

    factory = _make_session_factory([[]])
    producer = _make_producer()

    published = await core.backfill(
        producer=producer,
        session_factory=factory,
        lag_probe=MemoryLagProbe(),
        lag_topic="players.banned",
        lag_group_id="ban_migration_worker",
        batch_size=10,
    )

    assert published == 0
    producer.put.assert_not_awaited()


@pytest.mark.asyncio
async def test_backfill_throttles_when_lag_exceeds_max(monkeypatch):
    """When lag >= max_lag the run sleeps and re-probes without producing."""
    sleep = AsyncMock(return_value=None)
    monkeypatch.setattr(core.asyncio, "sleep", sleep)

    factory = _make_session_factory([[(1, "alice"), (2, "bob")], []])
    producer = _make_producer()
    # First probe over threshold (throttle), second clear, third ends the loop.
    lag_probe = _ScriptedLagProbe([200_000, 0, 0])

    published = await core.backfill(
        producer=producer,
        session_factory=factory,
        lag_probe=lag_probe,
        lag_topic="players.banned",
        lag_group_id="ban_migration_worker",
        batch_size=10,
        max_lag=100_000,
        lag_sleep_seconds=5,
    )

    # Throttled once, then resumed and produced both events.
    assert sleep.await_count == 1
    assert sleep.await_args is not None
    assert sleep.await_args.args[0] == 5
    assert published == 2
    assert producer.put.await_count >= 1


@pytest.mark.asyncio
async def test_backfill_aborts_on_producer_error(monkeypatch):
    """A producer error aborts the run by re-raising."""
    monkeypatch.setattr(core.asyncio, "sleep", AsyncMock(return_value=None))

    factory = _make_session_factory([[(1, "alice"), (2, "bob")], []])
    producer = _make_producer()
    producer.put = AsyncMock(return_value=Exception("broker down"))

    with pytest.raises(Exception, match="broker down"):
        await core.backfill(
            producer=producer,
            session_factory=factory,
            lag_probe=MemoryLagProbe(),
            lag_topic="players.banned",
            lag_group_id="ban_migration_worker",
            batch_size=10,
        )

    # First put() returned an error and aborted; no further calls.
    assert producer.put.await_count == 1
