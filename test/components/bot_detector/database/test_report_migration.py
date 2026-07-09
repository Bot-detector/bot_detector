from unittest.mock import AsyncMock, MagicMock

import pytest
from bot_detector.database.report import migrate_banned_player_reports


def _make_session_factory(rowcount: int):
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(rowcount=rowcount))

    begin_cm = AsyncMock()
    begin_cm.__aenter__ = AsyncMock(return_value=None)
    begin_cm.__aexit__ = AsyncMock(return_value=None)
    session.begin = MagicMock(return_value=begin_cm)

    session_cm = AsyncMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=None)

    return MagicMock(return_value=session_cm), session


@pytest.mark.asyncio
async def test_migrate_inserts_rows_for_reported_player():
    factory, session = _make_session_factory(rowcount=5)

    inserted = await migrate_banned_player_reports(factory, reported_id=42)

    assert inserted == 5
    call = session.execute.call_args
    sql_text = call.args[0].text
    params = call.kwargs["params"]

    assert "INSERT IGNORE" in sql_text
    assert "report_archive" in sql_text
    assert params["reported_id"] == 42


@pytest.mark.asyncio
async def test_migrate_is_idempotent_second_run_inserts_zero():
    # copy semantics: a re-run finds nothing new to insert (PK dedup)
    factory, session = _make_session_factory(rowcount=0)

    inserted = await migrate_banned_player_reports(factory, reported_id=42)

    assert inserted == 0


@pytest.mark.asyncio
async def test_migrate_does_not_delete_source_rows():
    factory, session = _make_session_factory(rowcount=5)

    await migrate_banned_player_reports(factory, reported_id=42)

    sql_text = session.execute.call_args.args[0].text
    # migration is copy-only; the source `report` table must not be deleted
    assert "DELETE" not in sql_text.upper()
