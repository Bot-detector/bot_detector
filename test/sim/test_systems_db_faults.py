"""Tests for DB error factories + FaultSession wiring (A5 + C4)."""

from typing import Any

import pytest
from asyncmy.errors import OperationalError as AsyncMyOperationalError
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError

from dst.faults import DbFaultConfig
from dst.systems.db_faults import (
    ERR_DEADLOCK,
    ERR_DUP_KEY,
    ERR_LOCK_WAIT_TIMEOUT,
    ERR_TEMP_TABLE_FULL,
    ERR_TOO_MANY_CONNECTIONS,
    FaultSession,
    connection_lost_error,
    db_operational_error,
    deadlock_error,
    dup_key_error,
    lock_wait_timeout_error,
    temp_table_full_error,
    too_many_connections_error,
)
from dst.systems.sim_db import SimDB, TableSchema

REPORTS = TableSchema(
    name="reports",
    columns=("reporter_id", "reported_id", "timestamp", "region_id"),
    primary_key=("reporter_id", "reported_id", "timestamp"),
)


def make_session(seed: int = 7, **pcts: float) -> tuple[FaultSession, SimDB]:
    db = SimDB()
    db.define_table(REPORTS)
    return FaultSession(db, DbFaultConfig(**pcts), seed=seed), db


def row(i: int) -> dict[str, Any]:
    return {
        "reporter_id": i,
        "reported_id": i + 1,
        "timestamp": 1_700_000_000 + i,
        "region_id": i % 100,
    }


def errno_of(exc: DBAPIError) -> int:
    orig: Any = exc.orig
    return orig.errno


def test_operational_error_wraps_asyncmy_orig_with_errno():
    err = db_operational_error(1213, "Deadlock found", "INSERT ...", {"a": 1})
    assert isinstance(err, OperationalError)
    assert isinstance(err.orig, AsyncMyOperationalError)
    orig: Any = err.orig
    assert errno_of(err) == 1213
    assert orig.args == (1213, "Deadlock found")
    assert err.statement == "INSERT ..."


def test_connection_lost_sets_connection_invalidated():
    for errno in (2006, 2013):
        err = db_operational_error(errno, "lost")
        assert isinstance(err, OperationalError)
        assert errno_of(err) == errno
        assert err.connection_invalidated is True


def test_non_connection_error_has_no_invalidation_flag():
    err = db_operational_error(1213, "Deadlock found")
    assert err.connection_invalidated is False


def test_connection_lost_alternates_errno_by_ordinal_parity():
    assert errno_of(connection_lost_error(0)) == 2006
    assert errno_of(connection_lost_error(1)) == 2013
    assert errno_of(connection_lost_error(2)) == 2006
    assert errno_of(connection_lost_error(3)) == 2013


@pytest.mark.parametrize(
    ("factory", "errno"),
    [
        (deadlock_error, ERR_DEADLOCK),
        (lock_wait_timeout_error, ERR_LOCK_WAIT_TIMEOUT),
        (too_many_connections_error, ERR_TOO_MANY_CONNECTIONS),
        (temp_table_full_error, ERR_TEMP_TABLE_FULL),
    ],
)
def test_operational_factories_use_their_knob_errno(factory: Any, errno: int):
    err = factory("INSERT ...")
    assert isinstance(err, OperationalError)
    assert errno_of(err) == errno


def test_temp_table_full_error_names_the_temp_table():
    err = temp_table_full_error()
    assert errno_of(err) == ERR_TEMP_TABLE_FULL
    assert "temp_report" in str(err.orig)


def test_dup_key_error_is_integrity_error_1062():
    err = dup_key_error("1", "reports.PRIMARY", "INSERT ...")
    assert isinstance(err, IntegrityError)
    assert errno_of(err) == ERR_DUP_KEY
    assert "reports.PRIMARY" in str(err.orig)


def test_fault_draw_raises_before_reaching_simdb():
    session, db = make_session(deadlock_pct=100.0)
    with pytest.raises(OperationalError) as exc_info:
        session.insert("reports", row(0))
    assert errno_of(exc_info.value) == ERR_DEADLOCK
    assert db.count("reports") == 0
    assert session.faults_raised == {"1213": 1}


def test_zero_pct_never_faults_and_delegates():
    session, db = make_session(deadlock_pct=0.0, conn_lost_pct=0.0)
    for i in range(500):
        assert session.insert_ignore("reports", row(i)) == 1
    assert session.faults_raised == {}
    assert db.count("reports") == 500


def test_bucket_order_follows_config_field_order():
    cases: list[tuple[dict[str, float], int, type[DBAPIError]]] = [
        ({"deadlock_pct": 100.0}, ERR_DEADLOCK, OperationalError),
        ({"lock_wait_timeout_pct": 100.0}, ERR_LOCK_WAIT_TIMEOUT, OperationalError),
        ({"conn_lost_pct": 100.0}, 2006, OperationalError),
        ({"too_many_conn_pct": 100.0}, ERR_TOO_MANY_CONNECTIONS, OperationalError),
        ({"temp_table_full_pct": 100.0}, ERR_TEMP_TABLE_FULL, OperationalError),
        ({"dup_key_pct": 100.0}, ERR_DUP_KEY, IntegrityError),
    ]
    for pcts, errno, exc_class in cases:
        db = SimDB()
        db.define_table(REPORTS)
        session = FaultSession(db, DbFaultConfig(**pcts), seed=7)
        with pytest.raises(exc_class) as exc_info:
            session.insert("reports", row(0))
        assert errno_of(exc_info.value) == errno


def test_pool_timeout_bucket_is_excluded():
    session, db = make_session(pool_timeout_pct=100.0)
    assert session.insert("reports", row(0)) == 1
    assert session.faults_raised == {}
    assert db.count("reports") == 1


def test_conn_lost_faults_alternate_parity_across_ops():
    session, _db = make_session(conn_lost_pct=100.0)
    seen: list[int] = []
    for _ in range(4):
        with pytest.raises(OperationalError) as exc_info:
            session.insert("reports", row(0))
        seen.append(errno_of(exc_info.value))
    assert seen == [2006, 2013, 2006, 2013]
    assert session.faults_raised == {"2006": 2, "2013": 2}


def test_dup_key_bucket_fires_only_on_insert_and_upsert():
    session, db = make_session(dup_key_pct=100.0)
    with pytest.raises(IntegrityError):
        session.insert("reports", row(0))
    with pytest.raises(IntegrityError):
        session.upsert("reports", row(0))
    assert session.insert_ignore("reports", row(0)) == 1
    assert session.delete_limit("reports", lambda r: False, 10) == 0
    assert db.count("reports") == 1
    assert session.faults_raised == {"1062": 2}


def test_select_and_count_pass_through_without_faults():
    session, db = make_session(deadlock_pct=100.0)
    db.insert("reports", row(0))
    assert list(session.select("reports")) != []
    assert session.count("reports") == 1
    assert session.faults_raised == {}


def test_select_does_not_consume_fault_ordinals():
    session, db = make_session(conn_lost_pct=100.0)
    db.insert("reports", row(0))
    list(session.select("reports"))
    session.count("reports")
    with pytest.raises(OperationalError) as exc_info:
        session.insert("reports", row(0))
    assert errno_of(exc_info.value) == 2006  # ordinal 0 (even)


def _fault_pattern(seed: int) -> list[tuple[str, int | None]]:
    """Run one fixed op sequence; record op name and raised errno."""
    session, db = make_session(
        seed=seed, deadlock_pct=5, conn_lost_pct=5, dup_key_pct=5
    )
    pattern: list[tuple[str, int | None]] = []
    for i in range(200):
        for op, args in (
            ("insert", row(i)),
            ("insert_ignore", row(i + 1000)),
            ("upsert", row(i + 2000)),
        ):
            try:
                getattr(session, op)("reports", args)
                pattern.append((op, None))
            except (OperationalError, IntegrityError) as exc:
                pattern.append((op, errno_of(exc)))
    _ = db.count("reports")
    return pattern


def test_same_seed_replays_same_fault_pattern():
    assert _fault_pattern(7) == _fault_pattern(7)


def test_fault_counters_accumulate_per_errno():
    session, db = make_session(deadlock_pct=100.0)
    for _ in range(3):
        with pytest.raises(OperationalError):
            session.insert("reports", row(0))
    assert session.faults_raised == {"1213": 3}
    assert session.faults_raised_total == 3
    assert db.count("reports") == 0
