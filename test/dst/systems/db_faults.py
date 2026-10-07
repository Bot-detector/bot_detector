"""DB fault factories and FaultSession (spec A5 + C4).

Factories raise/return the real SQLAlchemy errors the product sees:
``sqlalchemy.exc.OperationalError(stmt, params, orig)`` with ``orig``
an ``asyncmy.errors.OperationalError(errno, msg)`` (errno 1062 goes to
``IntegrityError``). asyncmy only sets ``.errno`` inside
``raise_mysql_exception``, so the factories attach it manually to keep
``orig.errno`` checks working. Errnos 2006/2013 additionally set
``connection_invalidated=True`` on the SQLAlchemy error (spec
exceptions/sqlalchemy.md §2).

Stream/ordinal conventions (spec §4.1): one draw per fault-checked op
on stream ``db:x:<table>``; ``ordinal`` is the per-table op counter
kept by the session (correctness state, not fault state). Draw order
per op is FIXED:

    bucket(draw(seed, "db:x:<table>", ordinal),
           deadlock_pct,            # 1213
           lock_wait_timeout_pct,   # 1205
           conn_lost_pct,           # 2006 (even ordinal) / 2013 (odd)
           too_many_conn_pct,       # 1040
           temp_table_full_pct,     # 1114
           dup_key_pct)             # 1062, insert/upsert only

``pool_timeout_pct`` is excluded (checkout happens before any
statement). The dup_key bucket is inert on ops without a raise path
(``insert_ignore`` swallows 1062; ``delete_limit`` cannot dup): the
draw is consumed, no error is raised. ``select``/``count`` are
pass-through: no draw, no ordinal. Errors are RAISED here — this layer
models SQLAlchemy raise semantics (spec §3.3).
"""

from collections.abc import Callable, Iterator
from typing import Any

from asyncmy.errors import IntegrityError as AsyncMyIntegrityError
from asyncmy.errors import OperationalError as AsyncMyOperationalError
from sqlalchemy.exc import IntegrityError, OperationalError

from dst.faults import DbFaultConfig, bucket, draw
from dst.systems.sim_db import DEFAULT_BATCH_SIZE, SimDB

ERR_DEADLOCK = 1213
ERR_LOCK_WAIT_TIMEOUT = 1205
ERR_CONN_GONE_AWAY = 2006
ERR_CONN_LOST_DURING_QUERY = 2013
ERR_TOO_MANY_CONNECTIONS = 1040
ERR_TEMP_TABLE_FULL = 1114
ERR_DUP_KEY = 1062

CONN_LOST_ERRNOS = (ERR_CONN_GONE_AWAY, ERR_CONN_LOST_DURING_QUERY)

DEADLOCK_MSG = "Deadlock found when trying to get lock; try restarting transaction"
LOCK_WAIT_MSG = "Lock wait timeout exceeded; try restarting transaction"
GONE_AWAY_MSG = "MySQL server has gone away"
LOST_QUERY_MSG = "Lost connection to MySQL server during query"
TOO_MANY_CONN_MSG = "Too many connections"
TEMP_TABLE_FULL_MSG = "The table 'temp_report' is full"


def _asyncmy_operational(errno: int, msg: str) -> AsyncMyOperationalError:
    """asyncmy OperationalError with the errno attribute attached."""
    orig = AsyncMyOperationalError(errno, msg)
    orig.errno = errno
    return orig


def _asyncmy_integrity(errno: int, msg: str) -> AsyncMyIntegrityError:
    """asyncmy IntegrityError with the errno attribute attached."""
    orig = AsyncMyIntegrityError(errno, msg)
    orig.errno = errno
    return orig


def db_operational_error(
    errno: int, msg: str, statement: str = "", params: Any = None
) -> OperationalError:
    """Real OperationalError wrapping an asyncmy-shaped ``.orig``.

    Errnos 2006/2013 set ``connection_invalidated=True`` on the
    returned error (mimics SQLAlchemy's pool invalidation attribute).
    """

    error = OperationalError(statement, params, _asyncmy_operational(errno, msg))
    if errno in CONN_LOST_ERRNOS:
        error.connection_invalidated = True
    return error


def deadlock_error(statement: str = "", params: Any = None) -> OperationalError:
    """errno 1213 — retriable by restarting the transaction."""

    return db_operational_error(ERR_DEADLOCK, DEADLOCK_MSG, statement, params)


def lock_wait_timeout_error(
    statement: str = "", params: Any = None
) -> OperationalError:
    """errno 1205 — statement-level lock wait timeout."""

    return db_operational_error(ERR_LOCK_WAIT_TIMEOUT, LOCK_WAIT_MSG, statement, params)


def connection_lost_error(
    ordinal: int, statement: str = "", params: Any = None
) -> OperationalError:
    """errno 2006 (even ordinal) / 2013 (odd), connection_invalidated."""

    errno = ERR_CONN_GONE_AWAY if ordinal % 2 == 0 else ERR_CONN_LOST_DURING_QUERY
    msg = GONE_AWAY_MSG if errno == ERR_CONN_GONE_AWAY else LOST_QUERY_MSG
    return db_operational_error(errno, msg, statement, params)


def too_many_connections_error(
    statement: str = "", params: Any = None
) -> OperationalError:
    """errno 1040 — server connection cap hit (backpressure)."""

    return db_operational_error(
        ERR_TOO_MANY_CONNECTIONS, TOO_MANY_CONN_MSG, statement, params
    )


def temp_table_full_error(statement: str = "", params: Any = None) -> OperationalError:
    """errno 1114 — MEMORY heap limit on the temp_report staging table."""

    return db_operational_error(
        ERR_TEMP_TABLE_FULL, TEMP_TABLE_FULL_MSG, statement, params
    )


def dup_key_error(
    entry: str, key: str, statement: str = "", params: Any = None
) -> IntegrityError:
    """errno 1062 — expected on non-INSERT IGNORE races."""

    msg = f"Duplicate entry '{entry}' for key '{key}'"
    return IntegrityError(statement, params, _asyncmy_integrity(ERR_DUP_KEY, msg))


class FaultSession:
    """SimDB wrapper raising pct-driven faults before each statement.

    Mirrors the SimDB surface; every fault-checked op draws once per
    the module docstring's fixed order and raises the mapped real
    SQLAlchemy error before delegating to the wrapped SimDB.
    """

    def __init__(
        self, db: SimDB, faults: DbFaultConfig | None = None, seed: int = 0
    ) -> None:
        """Wrap a SimDB with statement faults.

        Args:
            db: The wrapped table engine.
            faults: Pct knobs; defaults to an all-zero (never-fault)
                config.
            seed: Run-level seed every draw derives from.
        """
        self.db = db
        self.faults = faults if faults is not None else DbFaultConfig()
        self.seed = seed
        self._ordinals: dict[str, int] = {}
        self.faults_raised: dict[str, int] = {}

    @property
    def faults_raised_total(self) -> int:
        """Total faults raised across all errnos."""
        return sum(self.faults_raised.values())

    def _record(self, errno: int) -> None:
        key = str(errno)
        self.faults_raised[key] = self.faults_raised.get(key, 0) + 1

    def _check(self, table: str, dup_key_applies: bool) -> None:
        """Draw once for this op; raise the mapped error on a hit."""
        stream = f"db:x:{table}"
        ordinal = self._ordinals.get(stream, 0)
        self._ordinals[stream] = ordinal + 1
        index = bucket(
            draw(self.seed, stream, ordinal),
            self.faults.deadlock_pct,
            self.faults.lock_wait_timeout_pct,
            self.faults.conn_lost_pct,
            self.faults.too_many_conn_pct,
            self.faults.temp_table_full_pct,
            self.faults.dup_key_pct,
        )
        errno = self._bucket_errno(index, ordinal, table, dup_key_applies)
        if errno is None:
            return
        self._record(errno)
        raise self._bucket_error(index, ordinal, table)

    def _bucket_errno(
        self, index: int, ordinal: int, table: str, dup_key_applies: bool
    ) -> int | None:
        """errno for a bucket hit, or None when the bucket is inert."""
        if index < 0:
            return None
        if index == 0:
            return ERR_DEADLOCK
        if index == 1:
            return ERR_LOCK_WAIT_TIMEOUT
        if index == 2:
            return (
                ERR_CONN_GONE_AWAY if ordinal % 2 == 0 else ERR_CONN_LOST_DURING_QUERY
            )
        if index == 3:
            return ERR_TOO_MANY_CONNECTIONS
        if index == 4:
            return ERR_TEMP_TABLE_FULL
        return ERR_DUP_KEY if dup_key_applies else None

    def _bucket_error(self, index: int, ordinal: int, table: str) -> Exception:
        """Build the real error for a raised bucket hit."""
        if index == 0:
            return deadlock_error()
        if index == 1:
            return lock_wait_timeout_error()
        if index == 2:
            return connection_lost_error(ordinal)
        if index == 3:
            return too_many_connections_error()
        if index == 4:
            return temp_table_full_error()
        return dup_key_error("sim", f"{table}.PRIMARY")

    def insert(self, table: str, row: dict[str, Any]) -> int:
        """INSERT; dup_key bucket applies, SimDB 1062 still possible."""
        self._check(table, dup_key_applies=True)
        return self.db.insert(table, row)

    def insert_ignore(self, table: str, row: dict[str, Any]) -> int:
        """INSERT IGNORE; dup_key bucket inert (1062 is swallowed)."""
        self._check(table, dup_key_applies=False)
        return self.db.insert_ignore(table, row)

    def upsert(self, table: str, row: dict[str, Any]) -> int:
        """ON DUPLICATE KEY UPDATE; dup_key bucket applies."""
        self._check(table, dup_key_applies=True)
        return self.db.upsert(table, row)

    def delete_limit(
        self,
        table: str,
        where: Callable[[dict[str, Any]], bool],
        limit: int,
    ) -> int:
        """DELETE ... LIMIT; dup_key bucket inert (cannot dup)."""
        self._check(table, dup_key_applies=False)
        return self.db.delete_limit(table, where, limit)

    def select(
        self,
        table: str,
        where: Callable[[dict[str, Any]], bool] | None = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> Iterator[list[dict[str, Any]]]:
        """Chunked select; pass-through, no fault draw, no ordinal."""
        return self.db.select(table, where, batch_size)

    def count(self, table: str) -> int:
        """Row count; pass-through, no fault draw, no ordinal."""
        return self.db.count(table)
