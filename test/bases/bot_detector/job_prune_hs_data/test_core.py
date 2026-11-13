import pytest
import sqlalchemy as sqla

from bot_detector.job_prune_hs_data import core


class FakeResult:
    def __init__(self, row: int | None = None, rowcount: int = 0) -> None:
        self._row = row
        self.rowcount = rowcount

    def first(self) -> int | None:
        return self._row


class FakeTransaction:
    async def __aenter__(self) -> "FakeTransaction":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


class FakeSession:
    def __init__(
        self,
        batch_ids: list[int] | None = None,
        rowcount: int = 0,
        error: Exception | None = None,
    ) -> None:
        self.batch_ids = batch_ids or []
        self.rowcount = rowcount
        self.error = error
        self.executed: list[tuple[str, dict[str, int] | None]] = []

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    def begin(self) -> FakeTransaction:
        return FakeTransaction()

    async def execute(
        self,
        sql: sqla.TextClause,
        params: dict[str, int] | None = None,
    ) -> FakeResult:
        statement = str(sql)
        self.executed.append((statement, params))
        if self.error is not None:
            raise self.error
        if "DELETE" in statement:
            return FakeResult(rowcount=self.rowcount)
        return FakeResult()

    async def scalars(
        self,
        sql: sqla.TextClause,
        params: dict[str, int] | None = None,
    ) -> FakeResult:
        statement = str(sql)
        self.executed.append((statement, params))
        return FakeResult(row=self.batch_ids[-1] if self.batch_ids else None)


class FakeSessionFactory:
    def __init__(self, sessions: list[FakeSession]) -> None:
        self._sessions = list(sessions)
        self.sessions: list[FakeSession] = []

    def __call__(self) -> FakeSession:
        session = self._sessions.pop(0)
        self.sessions.append(session)
        return session


def test_drop_temp_table_sql_is_temporary_only() -> None:
    assert "DROP TEMPORARY TABLE IF EXISTS" in str(core.drop_temp_table())


def test_insert_temp_table_sql_orders_by_id() -> None:
    assert "ORDER BY id" in str(core.insert_temp_table())


@pytest.mark.asyncio
async def test_prune_stops_on_empty_batch_without_deleting() -> None:
    factory = FakeSessionFactory([FakeSession(batch_ids=[])])
    await core.prune(factory, limit=100)  # type: ignore[arg-type]

    assert len(factory.sessions) == 1
    statements = [statement for statement, _ in factory.sessions[0].executed]
    assert not any("DELETE" in statement for statement in statements)


@pytest.mark.asyncio
async def test_prune_advances_cursor_to_batch_max_id() -> None:
    factory = FakeSessionFactory(
        [
            FakeSession(batch_ids=[150]),
            FakeSession(batch_ids=[300]),
            FakeSession(batch_ids=[]),
        ]
    )
    await core.prune(factory, limit=100)  # type: ignore[arg-type]

    assert len(factory.sessions) == 3
    first_insert = next(
        params
        for statement, params in factory.sessions[0].executed
        if "INSERT" in statement
    )
    second_insert = next(
        params
        for statement, params in factory.sessions[1].executed
        if "INSERT" in statement
    )
    assert first_insert == {"player_id": 0, "limit": 100}
    assert second_insert == {"player_id": 150, "limit": 100}
