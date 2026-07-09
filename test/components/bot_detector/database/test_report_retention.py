from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from bot_detector.database.report import prune_reports


def _make_session_factory(rowcounts: list[int]):
    """Build a session factory mock whose execute() returns rowcounts in order."""
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[MagicMock(rowcount=c) for c in rowcounts])

    begin_cm = AsyncMock()
    begin_cm.__aenter__ = AsyncMock(return_value=None)
    begin_cm.__aexit__ = AsyncMock(return_value=None)
    session.begin = MagicMock(return_value=begin_cm)

    session_cm = AsyncMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=None)

    return MagicMock(return_value=session_cm), session


@pytest.mark.asyncio
async def test_prune_reports_single_partial_batch():
    factory, session = _make_session_factory([3])

    total = await prune_reports(factory, older_than_days=90, batch_size=10_000)

    assert total == 3
    assert session.execute.await_count == 1


@pytest.mark.asyncio
async def test_prune_reports_loops_until_empty():
    factory, session = _make_session_factory([10_000, 10_000, 5])

    total = await prune_reports(factory, older_than_days=90, batch_size=10_000)

    assert total == 20_005
    assert session.execute.await_count == 3


@pytest.mark.asyncio
async def test_prune_reports_no_rows_returns_zero():
    factory, session = _make_session_factory([0])

    total = await prune_reports(factory, older_than_days=90, batch_size=10_000)

    assert total == 0
    assert session.execute.await_count == 1


@pytest.mark.asyncio
async def test_prune_reports_uses_age_cutoff_and_limit():
    factory, session = _make_session_factory([0])

    await prune_reports(factory, older_than_days=90, batch_size=5_000)

    call = session.execute.call_args
    sql_text = call.args[0].text
    params = call.kwargs["params"]

    assert "DELETE FROM report" in sql_text
    assert "reported_at" in sql_text
    assert "LIMIT" in sql_text
    assert params["batch_size"] == 5_000
    assert isinstance(params["cutoff"], datetime)
    # cutoff should be ~90 days ago
    assert params["cutoff"] <= datetime.now() - timedelta(days=89)
