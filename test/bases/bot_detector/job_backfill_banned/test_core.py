from unittest.mock import AsyncMock, MagicMock

import pytest
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


@pytest.mark.asyncio
async def test_backfill_paginates_and_migrates_each_player(monkeypatch):
    monkeypatch.setattr(core.asyncio, "sleep", AsyncMock(return_value=None))
    migrate = AsyncMock(side_effect=[5, 2, 7])
    monkeypatch.setattr(
        "bot_detector.job_backfill_banned.core.migrate_banned_player_reports",
        migrate,
    )

    factory = _make_session_factory([[1, 2, 3], []])

    processed = await core.backfill(factory, batch_size=10)

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

    processed = await core.backfill(factory, batch_size=10)

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

    processed = await core.backfill(factory, batch_size=10)

    assert processed == 0
    migrate.assert_not_awaited()
