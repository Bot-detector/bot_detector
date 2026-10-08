"""SimDB table engine: MySQL rowcount semantics over column stores.

Pure sync storage (spec C1): named tables of dict rows with primary-key
and unique index maps. Ops mirror the MySQL surfaces the product relies
on — INSERT, INSERT IGNORE, ON DUPLICATE KEY UPDATE, DELETE ... LIMIT —
and return MySQL rowcounts. Duplicate keys raise the real
``sqlalchemy.exc.IntegrityError`` (1062 shape, a semantic violation, not
a fault). No faults or SQL parsing here (C4). Select
is a chunked iterator per the lazy-data rule (spec §4.5).

C3 appends the async session proxy + pool occupancy model (SimPool,
SimSession, SimSessionPool): async_sessionmaker-shaped factory whose
sessions dispatch named SimDB ops. Occupancy-only pool — no per-op
latency; pre-ping/recycle cost (spec §5 lane C3, exceptions §5) is
deferred to the latency wave.
"""

import asyncio
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import (
    IntegrityError,
    ResourceClosedError,
    TimeoutError as PoolTimeoutError,
)

from dst.faults import DbFaultConfig, bucket, draw

DEFAULT_BATCH_SIZE = 1000

DupKey = tuple[int, str, tuple[Any, ...]]


class _MySQLError(Exception):
    """asyncmy-shaped error origin: (errno, message) with a typed errno."""

    def __init__(self, errno: int, message: str) -> None:
        super().__init__(errno, message)
        self.errno = errno


def _dup_entry_error(entry: str, key: str) -> IntegrityError:
    """IntegrityError shaped like MySQL errno 1062 via asyncmy."""
    orig = _MySQLError(1062, f"Duplicate entry '{entry}' for key '{key}'")
    return IntegrityError("", {}, orig)


@dataclass(frozen=True)
class TableSchema:
    """Column layout: name, columns, primary key, unique column groups."""

    name: str
    columns: tuple[str, ...]
    primary_key: tuple[str, ...]
    unique_constraints: tuple[tuple[str, ...], ...] = ()


class _Table:
    """Row store plus pk/unique index maps for one table."""

    def __init__(self, schema: TableSchema) -> None:
        self.schema = schema
        self.rows: list[dict[str, Any]] = []
        self.pk_index: dict[tuple[Any, ...], int] = {}
        self.unique_indexes: list[dict[tuple[Any, ...], int]] = [
            {} for _ in schema.unique_constraints
        ]

    def values(self, row: dict[str, Any], cols: tuple[str, ...]) -> tuple[Any, ...]:
        return tuple(row[c] for c in cols)

    def find_dup(self, row: dict[str, Any]) -> DupKey | None:
        """(row_index, key_name, key_values) of the first violated key."""
        key = self.values(row, self.schema.primary_key)
        if key in self.pk_index:
            return self.pk_index[key], "PRIMARY", key
        for cols, index in zip(
            self.schema.unique_constraints, self.unique_indexes, strict=True
        ):
            key = self.values(row, cols)
            if key in index:
                return index[key], "_".join(cols), key
        return None

    def append(self, row: dict[str, Any]) -> None:
        idx = len(self.rows)
        self.rows.append(dict(row))
        self.pk_index[self.values(row, self.schema.primary_key)] = idx
        for cols, index in zip(
            self.schema.unique_constraints, self.unique_indexes, strict=True
        ):
            index[self.values(row, cols)] = idx

    def remove_at(self, idx: int) -> None:
        """Swap-pop removal; maps stay consistent without O(n) rebuilds."""
        victim = self.rows[idx]
        del self.pk_index[self.values(victim, self.schema.primary_key)]
        for cols, index in zip(
            self.schema.unique_constraints, self.unique_indexes, strict=True
        ):
            del index[self.values(victim, cols)]
        last = len(self.rows) - 1
        if idx == last:
            self.rows.pop()
            return
        moved = self.rows.pop()
        self.rows[idx] = moved
        self.pk_index[self.values(moved, self.schema.primary_key)] = idx
        for cols, index in zip(
            self.schema.unique_constraints, self.unique_indexes, strict=True
        ):
            index[self.values(moved, cols)] = idx


class SimDB:
    """In-memory table engine with MySQL rowcount semantics."""

    def __init__(self) -> None:
        self._tables: dict[str, _Table] = {}

    def define_table(self, schema: TableSchema) -> None:
        """Register a table layout; names must be unique."""
        if schema.name in self._tables:
            raise ValueError(f"table already defined: {schema.name}")
        self._tables[schema.name] = _Table(schema)

    def _table(self, name: str) -> _Table:
        try:
            return self._tables[name]
        except KeyError:
            raise KeyError(f"unknown table: {name}") from None

    def insert(self, table: str, row: dict[str, Any]) -> int:
        """INSERT; duplicate pk/unique raises IntegrityError (1062)."""
        t = self._table(table)
        dup = t.find_dup(row)
        if dup is not None:
            _idx, key_name, key_values = dup
            entry = ",".join(str(v) for v in key_values)
            raise _dup_entry_error(entry, f"{table}.{key_name}")
        t.append(row)
        return 1

    def insert_ignore(self, table: str, row: dict[str, Any]) -> int:
        """INSERT IGNORE; dup is skipped, rowcount 0 instead of a raise."""
        t = self._table(table)
        if t.find_dup(row) is not None:
            return 0
        t.append(row)
        return 1

    def upsert(self, table: str, row: dict[str, Any]) -> int:
        """ON DUPLICATE KEY UPDATE; 1 inserted, 2 existing row updated."""
        t = self._table(table)
        dup = t.find_dup(row)
        if dup is None:
            t.append(row)
            return 1
        existing_idx, _key_name, _key_values = dup
        t.rows[existing_idx] = dict(row)
        return 2

    def delete_limit(
        self,
        table: str,
        where: Callable[[dict[str, Any]], bool],
        limit: int,
    ) -> int:
        """DELETE ... WHERE ... LIMIT; returns the rowcount (<= limit)."""
        t = self._table(table)
        victims = [i for i, r in enumerate(t.rows) if where(r)][:limit]
        for i in reversed(victims):
            t.remove_at(i)
        return len(victims)

    def select(
        self,
        table: str,
        where: Callable[[dict[str, Any]], bool] | None = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> Iterator[list[dict[str, Any]]]:
        """Chunked row batches (never the whole table); rows are copies."""
        t = self._table(table)
        if batch_size < 1:
            raise ValueError(f"batch_size must be >= 1, got {batch_size}")
        batch: list[dict[str, Any]] = []
        for row in t.rows:
            if where is not None and not where(row):
                continue
            batch.append(dict(row))
            if len(batch) == batch_size:
                yield batch
                batch = []
        if batch:
            yield batch

    def count(self, table: str) -> int:
        """Number of rows in the table."""
        return len(self._table(table).rows)


# --- C3: async session proxy + pool occupancy model --------------------

POOL_STREAM = "db:pool"

_ALLOWED_OPS: frozenset[str] = frozenset(
    {"insert", "insert_ignore", "upsert", "delete_limit", "select", "count"}
)


class SimPoolConfig(BaseModel):
    """Pool settings mirroring database/core.py engine wiring."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    size: int = Field(default=10, ge=1)
    max_overflow: int = Field(default=90, ge=0)
    timeout_s: float = Field(default=25.0, ge=0.0)


class SimPool:
    """Occupancy-only QueuePool model.

    No connection objects: checkout counts concurrent sessions against
    ``size + max_overflow``; past the limit it raises the real
    ``sqlalchemy.exc.TimeoutError`` with the QueuePool message shape,
    after a zero-cost virtual wait (one ``asyncio.sleep(0)`` yield on
    the running loop). Behavior depends only on occupancy, never on
    time or seed. ``pool_timeout_pct`` (spec §3.3) is the one seed-dependent
    path: with pct > 0, each checkout draws stream "db:pool" and a hit
    forces the same TimeoutError. Pre-ping/recycle cost is deferred to
    the latency wave (spec §5 lane C3; spec/exceptions §5).
    """

    def __init__(
        self,
        config: SimPoolConfig | None = None,
        faults: DbFaultConfig | None = None,
        seed: int = 0,
    ) -> None:
        self._config = config if config is not None else SimPoolConfig()
        self._faults = faults
        self._seed = seed
        self._ordinal = 0
        self._checked_out = 0

    @property
    def checked_out(self) -> int:
        """Current concurrent sessions (occupancy)."""
        return self._checked_out

    def _timeout_error(self) -> PoolTimeoutError:
        cfg = self._config
        return PoolTimeoutError(
            f"QueuePool limit of size {cfg.size} overflow {cfg.max_overflow} "
            f"reached, connection timed out, timeout {cfg.timeout_s:.2f}"
        )

    def _fault_forced(self) -> bool:
        """Advance the db:pool stream only when the knob is active."""
        if self._faults is None or self._faults.pool_timeout_pct <= 0.0:
            return False
        value = draw(self._seed, POOL_STREAM, self._ordinal)
        self._ordinal += 1
        return bucket(value, self._faults.pool_timeout_pct) == 0

    async def checkout(self) -> None:
        """Take one slot or raise the QueuePool checkout TimeoutError."""
        if self._fault_forced() or self._checked_out >= (
            self._config.size + self._config.max_overflow
        ):
            await asyncio.sleep(0)
            raise self._timeout_error()
        self._checked_out += 1

    def checkin(self) -> None:
        """Return one slot; never negative."""
        if self._checked_out > 0:
            self._checked_out -= 1


class SimSession:
    """AsyncSession-shaped proxy over SimDB: the used surface only (§3.3).

    ``execute(op_name, table, **kwargs)`` dispatches named SimDB ops —
    no SQL parsing this wave. ``commit``/``rollback`` are no-op markers
    (the row store is autocommit at op granularity); ``close`` releases
    pool occupancy exactly once, idempotently like AsyncSession.
    """

    def __init__(self, db: SimDB, pool: SimPool) -> None:
        self._db = db
        self._pool = pool
        self._closed = True

    async def _enter(self) -> "SimSession":
        await self._pool.checkout()
        self._closed = False
        return self

    async def __aenter__(self) -> "SimSession":
        return await self._enter()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        await self.close()

    async def execute(self, op_name: str, table: str, **kwargs: Any) -> Any:
        """Dispatch one named SimDB op; returns its rowcount or iterator."""
        if self._closed:
            raise ResourceClosedError("this SimSession is closed")
        if op_name not in _ALLOWED_OPS:
            raise ValueError(f"unsupported op: {op_name}")
        op: Callable[..., Any] = getattr(self._db, op_name)
        return op(table, **kwargs)

    async def commit(self) -> None:
        """No-op: SimDB ops apply immediately (no txn buffer this wave)."""

    async def rollback(self) -> None:
        """No-op marker; see :meth:`commit`."""

    async def close(self) -> None:
        """Release the pool slot once; further closes are no-ops."""
        if not self._closed:
            self._closed = True
            self._pool.checkin()


class SimSessionPool:
    """``async_sessionmaker``-shaped factory over SimDB + SimPool (§5.3)."""

    def __init__(
        self,
        db: SimDB,
        config: SimPoolConfig | None = None,
        faults: DbFaultConfig | None = None,
        seed: int = 0,
    ) -> None:
        self._db = db
        self._pool = SimPool(config=config, faults=faults, seed=seed)

    @property
    def pool(self) -> SimPool:
        return self._pool

    def session(self) -> SimSession:
        """Factory: use as ``async with pool.session() as session``."""
        return SimSession(self._db, self._pool)

    async def acquire(self) -> SimSession:
        """Checked-out session; caller must ``await session.close()``."""
        return await self.session()._enter()

    def __call__(self) -> SimSession:
        return self.session()
