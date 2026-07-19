from unittest.mock import AsyncMock, MagicMock

import pytest
from bot_detector.event_queue.adapters.memory import MemoryLagProbe
from bot_detector.event_queue.lag_probe import LagProbeProtocol
from bot_detector.job_backfill_banned import core


def _make_session_factory(pages: list[list[int]]):
    """Build a session factory whose execute() returns paged id lists."""
    session = AsyncMock()
    results = []
    for page in pages:
        result = MagicMock()
        result.scalars.return_value.all.return_value = page
        results.append(result)
    session.execute = AsyncMock(side_effect=results)

    session_cm = AsyncMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=None)

    return MagicMock(return_value=session_cm)


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
async def test_backfill_paginates_and_migrates_each_player(monkeypatch):
    monkeypatch.setattr(core.asyncio, "sleep", AsyncMock(return_value=None))
    migrate = AsyncMock(side_effect=[5, 2, 7])
    monkeypatch.setattr(
        "bot_detector.job_backfill_banned.core.migrate_banned_player_reports",
        migrate,
    )

    factory = _make_session_factory([[1, 2, 3], []])

    processed = await core.backfill(
        factory,
        lag_probe=MemoryLagProbe(),
        lag_topic="players.banned",
        lag_group_id="ban_migration_worker",
        batch_size=10,
    )

    assert processed == 3
    assert migrate.await_count == 3
    reported_ids = [c.kwargs["reported_id"] for c in migrate.call_args_list]
    assert reported_ids == [1, 2, 3]


@pytest.mark.asyncio
async def test_backfill_skips_on_error_and_continues(monkeypatch):
    monkeypatch.setattr(core.asyncio, "sleep", AsyncMock(return_value=None))
    migrate = AsyncMock(side_effect=[5, Exception("boom"), 2])
    monkeypatch.setattr(
        "bot_detector.job_backfill_banned.core.migrate_banned_player_reports",
        migrate,
    )

    factory = _make_session_factory([[1, 2, 3], []])

    processed = await core.backfill(
        factory,
        lag_probe=MemoryLagProbe(),
        lag_topic="players.banned",
        lag_group_id="ban_migration_worker",
        batch_size=10,
    )

    # second player errored and is skipped; first and third succeed
    assert processed == 2
    assert migrate.await_count == 3


@pytest.mark.asyncio
async def test_backfill_terminates_when_no_banned_players(monkeypatch):
    monkeypatch.setattr(core.asyncio, "sleep", AsyncMock(return_value=None))
    migrate = AsyncMock()
    monkeypatch.setattr(
        "bot_detector.job_backfill_banned.core.migrate_banned_player_reports",
        migrate,
    )

    factory = _make_session_factory([[]])

    processed = await core.backfill(
        factory,
        lag_probe=MemoryLagProbe(),
        lag_topic="players.banned",
        lag_group_id="ban_migration_worker",
        batch_size=10,
    )

    assert processed == 0
    migrate.assert_not_awaited()


@pytest.mark.asyncio
async def test_backfill_throttles_when_lag_exceeds_max(monkeypatch):
    """When lag >= max_lag the run sleeps and re-probes without fetching."""
    sleep = AsyncMock(return_value=None)
    monkeypatch.setattr(core.asyncio, "sleep", sleep)

    migrate = AsyncMock(side_effect=[5, 2])
    monkeypatch.setattr(
        "bot_detector.job_backfill_banned.core.migrate_banned_player_reports",
        migrate,
    )

    factory = _make_session_factory([[1, 2], []])
    # First probe is over threshold (throttle), second is clear, third ends the
    # pagination loop.
    lag_probe = _ScriptedLagProbe([200_000, 0, 0])

    processed = await core.backfill(
        factory,
        lag_probe=lag_probe,
        lag_topic="players.banned",
        lag_group_id="ban_migration_worker",
        batch_size=10,
        max_lag=100_000,
        lag_sleep_seconds=5,
    )

    # Throttled once, then resumed and migrated both players.
    assert sleep.await_count == 1
    assert sleep.await_args.args[0] == 5
    assert processed == 2
    assert migrate.await_count == 2
