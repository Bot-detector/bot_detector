import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot_detector.event_queue.structs import ReportsToInsertStruct
from bot_detector.structs._metadata import MetaData
from bot_detector.structs.reports import Equipment, ParsedDetection
from bot_detector.worker_report.adapter import transform_report
from bot_detector.worker_report.worker import ReportWorker, insert_batch


def _build_parsed_detection(**overrides) -> ParsedDetection:
    defaults = dict(
        reporter_id=1,
        reported_id=2,
        region_id=0,
        x_coord=0,
        y_coord=0,
        z_coord=0,
        ts=int(time.time()),
        manual_detect=0,
        on_members_world=0,
        on_pvp_world=0,
        world_number=500,
        equipment=Equipment(),
        equip_ge_value=0,
    )
    defaults.update(overrides)
    return ParsedDetection(**defaults)


def _build_report_struct(
    version: int = 1, **detection_overrides
) -> ReportsToInsertStruct:
    return ReportsToInsertStruct(
        metadata=MetaData(version=version, source="test"),
        report=_build_parsed_detection(**detection_overrides),
    )


def test_transform_report_v1_returns_detection():
    record = _build_report_struct(version=1)
    result = transform_report(record)
    assert result is not None
    assert isinstance(result, ParsedDetection)
    assert result.reporter_id == 1


def test_transform_report_unsupported_version_returns_none():
    record = _build_report_struct(version=2)
    result = transform_report(record)
    assert result is None


@pytest.mark.asyncio
async def test_insert_batch_calls_repo():
    batch = [_build_parsed_detection(), _build_parsed_detection()]
    session = AsyncMock()
    session.begin = MagicMock(return_value=AsyncMock())

    session_factory = MagicMock()
    session_factory.return_value.__aenter__ = AsyncMock(return_value=session)
    session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

    report_repo = AsyncMock()

    await insert_batch(
        report_repo=report_repo,
        batch=batch,
        session_factory=session_factory,
    )

    report_repo.insert.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_calls_insert_batch():
    batch = [_build_report_struct(version=1)]
    session_factory = MagicMock()
    report_repo = AsyncMock()

    w = ReportWorker(
        worker_id=0,
        session_factory=session_factory,
        report_repo=report_repo,
    )

    with patch(
        "bot_detector.worker_report.worker.insert_batch", new_callable=AsyncMock
    ) as mock_insert:
        await w.handle(batch)

    mock_insert.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_skips_invalid_versions():
    batch = [_build_report_struct(version=2)]
    session_factory = MagicMock()
    report_repo = AsyncMock()

    w = ReportWorker(
        worker_id=0,
        session_factory=session_factory,
        report_repo=report_repo,
    )

    await w.handle(batch)

    report_repo.insert.assert_not_awaited()
