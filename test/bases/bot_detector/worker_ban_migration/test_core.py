from unittest.mock import AsyncMock

import pytest
from bot_detector.event_queue.structs import PlayerBannedStruct
from bot_detector.structs import MetaData
from bot_detector.worker_ban_migration.adapter import transform_player_banned
from bot_detector.worker_ban_migration.worker import BanMigrationWorker


def _banned_struct(version: int = 1, player_id: int = 7) -> PlayerBannedStruct:
    return PlayerBannedStruct(
        metadata=MetaData(version=version, source="test"),
        player_id=player_id,
        name="banned_player",
    )


def test_transform_v1_returns_player_id():
    assert transform_player_banned(_banned_struct(version=1, player_id=7)) == 7


def test_transform_unsupported_version_returns_none():
    assert transform_player_banned(_banned_struct(version=2)) is None


@pytest.mark.asyncio
async def test_handle_migrates_each_valid_record(monkeypatch):
    migrate = AsyncMock(side_effect=[5, 3])
    monkeypatch.setattr(
        "bot_detector.worker_ban_migration.worker.migrate_banned_player_reports",
        migrate,
    )

    worker = BanMigrationWorker(worker_id=0, session_factory=AsyncMock())
    result = await worker.handle(
        [_banned_struct(player_id=1), _banned_struct(player_id=2)]
    )

    assert migrate.await_count == 2
    # reported_id passed through to the migration function
    assert migrate.call_args_list[0].kwargs["reported_id"] == 1
    assert migrate.call_args_list[1].kwargs["reported_id"] == 2
    # Full success -> nothing to requeue.
    assert result == []


@pytest.mark.asyncio
async def test_handle_skips_invalid_version(monkeypatch):
    migrate = AsyncMock()
    monkeypatch.setattr(
        "bot_detector.worker_ban_migration.worker.migrate_banned_player_reports",
        migrate,
    )

    worker = BanMigrationWorker(worker_id=0, session_factory=AsyncMock())
    result = await worker.handle([_banned_struct(version=2, player_id=9)])

    migrate.assert_not_awaited()
    # Skipped (unsupported version) is not a failure -> not requeued.
    assert result == []


@pytest.mark.asyncio
async def test_handle_returns_failed_records_for_requeue(monkeypatch):
    """A per-record DB failure isolates the failing record; the rest progress."""
    migrate = AsyncMock(side_effect=[5, Exception("db down"), 3])
    monkeypatch.setattr(
        "bot_detector.worker_ban_migration.worker.migrate_banned_player_reports",
        migrate,
    )

    worker = BanMigrationWorker(worker_id=0, session_factory=AsyncMock())
    records = [
        _banned_struct(player_id=1),
        _banned_struct(player_id=2),
        _banned_struct(player_id=3),
    ]
    failed = await worker.handle(records)

    # Every record was attempted; the failure did not abort the batch.
    assert migrate.await_count == 3
    # Only the failed record is returned for requeue.
    assert len(failed) == 1
    assert failed[0].player_id == 2
