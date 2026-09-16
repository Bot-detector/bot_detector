from unittest.mock import AsyncMock, MagicMock

import pytest
from bot_detector.event_queue.structs import ReportsToInsertStruct
from bot_detector.structs import ParsedDetection
from bot_detector.structs._metadata import MetaData
from bot_detector.structs.reports import Equipment
from bot_detector.worker_report.worker import ReportWorker, insert_batch
from prometheus_client import REGISTRY


def _build_report(version: int = 1) -> ReportsToInsertStruct:
    return ReportsToInsertStruct(
        metadata=MetaData(version=version, source="test"),
        report=ParsedDetection(
            reporter_id=1,
            reported_id=2,
            equipment=Equipment(),
        ),
    )


def _sample(name: str) -> float | None:
    return REGISTRY.get_sample_value(name)


def _mock_session_factory() -> MagicMock:
    session = AsyncMock()
    session.begin = MagicMock(return_value=AsyncMock())
    session_factory = MagicMock()
    session_factory.return_value.__aenter__ = AsyncMock(return_value=session)
    session_factory.return_value.__aexit__ = AsyncMock(return_value=None)
    return session_factory


@pytest.mark.asyncio
async def test_insert_batch_increments_inserted_counter():
    batch = [_build_report(), _build_report()]
    before = _sample("report_worker_reports_inserted_total") or 0

    await insert_batch(
        report_repo=AsyncMock(),
        batch=batch,
        session_factory=_mock_session_factory(),
    )

    assert (_sample("report_worker_reports_inserted_total") or 0) == before + 2


@pytest.mark.asyncio
async def test_handle_counts_dropped_invalid_reports():
    batch = [_build_report(version=1), _build_report(version=2)]
    before = _sample("report_worker_reports_dropped_total") or 0

    worker = ReportWorker(
        worker_id=0,
        session_factory=_mock_session_factory(),
        report_repo=AsyncMock(),
    )
    await worker.handle(batch)

    assert (_sample("report_worker_reports_dropped_total") or 0) == before + 1
