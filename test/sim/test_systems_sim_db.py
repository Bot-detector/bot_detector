"""Tests for the SimDB table engine (MySQL rowcount semantics)."""

import asyncio
from typing import Any

import pytest
from sqlalchemy.exc import IntegrityError, TimeoutError

from dst.faults import DbFaultConfig
from dst.systems.sim_db import SimDB, SimPoolConfig, SimSessionPool, TableSchema

PLAYERS = TableSchema(
    name="players",
    columns=("id", "name", "status"),
    primary_key=("id",),
    unique_constraints=(("name",),),
)


def make_db() -> SimDB:
    db = SimDB()
    db.define_table(PLAYERS)
    return db


def test_insert_returns_one_and_counts_rows():
    db = make_db()
    assert db.insert("players", {"id": 1, "name": "a", "status": "new"}) == 1
    assert db.insert("players", {"id": 2, "name": "b", "status": "new"}) == 1
    assert db.count("players") == 2


def test_insert_duplicate_pk_raises_integrity_error():
    db = make_db()
    db.insert("players", {"id": 1, "name": "a", "status": "new"})
    with pytest.raises(IntegrityError) as exc_info:
        db.insert("players", {"id": 1, "name": "b", "status": "new"})
    orig: Any = exc_info.value.orig
    assert orig.errno == 1062
    assert "players.PRIMARY" in str(orig)


def test_insert_duplicate_unique_raises_integrity_error():
    db = make_db()
    db.insert("players", {"id": 1, "name": "a", "status": "new"})
    with pytest.raises(IntegrityError) as exc_info:
        db.insert("players", {"id": 2, "name": "a", "status": "new"})
    orig: Any = exc_info.value.orig
    assert orig.errno == 1062
    assert "players.name" in str(orig)


def test_insert_ignore_rowcounts():
    db = make_db()
    assert db.insert_ignore("players", {"id": 1, "name": "a", "status": "x"}) == 1
    assert db.insert_ignore("players", {"id": 1, "name": "b", "status": "y"}) == 0
    assert db.insert_ignore("players", {"id": 2, "name": "a", "status": "z"}) == 0
    assert db.count("players") == 1


def test_upsert_insert_returns_one():
    db = make_db()
    assert db.upsert("players", {"id": 1, "name": "a", "status": "new"}) == 1
    assert db.count("players") == 1


def test_upsert_existing_returns_two_and_updates():
    db = make_db()
    db.insert("players", {"id": 1, "name": "a", "status": "old"})
    assert db.upsert("players", {"id": 1, "name": "a", "status": "new"}) == 2
    assert db.count("players") == 1
    batches = list(db.select("players"))
    assert len(batches) == 1
    assert batches[0][0]["status"] == "new"


def test_delete_limit_counts_and_respects_limit():
    db = make_db()
    for i in range(5):
        status = "old" if i < 3 else "new"
        db.insert("players", {"id": i, "name": f"n{i}", "status": status})
    assert db.delete_limit("players", lambda r: r["status"] == "old", 2) == 2
    assert db.count("players") == 3
    assert db.delete_limit("players", lambda r: r["status"] == "old", 10) == 1
    assert db.count("players") == 2
    remaining = [r["id"] for batch in db.select("players") for r in batch]
    assert remaining == [3, 4]


def test_select_chunks_in_batches_with_partial_last():
    db = make_db()
    for i in range(2500):
        db.insert("players", {"id": i, "name": f"n{i}", "status": "new"})
    sizes = [len(batch) for batch in db.select("players")]
    assert sizes == [1000, 1000, 500]


def test_select_custom_batch_size_and_total():
    db = make_db()
    for i in range(1000):
        db.insert("players", {"id": i, "name": f"n{i}", "status": "new"})
    batches = list(db.select("players", batch_size=700))
    assert [len(b) for b in batches] == [700, 300]
    total = sum(len(b) for b in batches)
    assert total == 1000


def test_select_where_filters_rows():
    db = make_db()
    for i in range(5):
        status = "old" if i % 2 else "new"
        db.insert("players", {"id": i, "name": f"n{i}", "status": status})
    rows = [
        r
        for batch in db.select("players", lambda r: r["status"] == "old")
        for r in batch
    ]
    assert [r["id"] for r in rows] == [1, 3]


def test_composite_unique_constraint():
    schema = TableSchema(
        name="links",
        columns=("id", "src", "dst"),
        primary_key=("id",),
        unique_constraints=(("src", "dst"),),
    )
    db = SimDB()
    db.define_table(schema)
    assert db.insert("links", {"id": 1, "src": "a", "dst": "b"}) == 1
    assert db.insert("links", {"id": 2, "src": "a", "dst": "c"}) == 1
    with pytest.raises(IntegrityError):
        db.insert("links", {"id": 3, "src": "a", "dst": "b"})


def test_composite_pk():
    schema = TableSchema(
        name="pairs",
        columns=("a", "b", "v"),
        primary_key=("a", "b"),
    )
    db = SimDB()
    db.define_table(schema)
    assert db.insert("pairs", {"a": 1, "b": 2, "v": "x"}) == 1
    assert db.insert("pairs", {"a": 1, "b": 3, "v": "y"}) == 1
    with pytest.raises(IntegrityError):
        db.insert("pairs", {"a": 1, "b": 2, "v": "z"})


def test_bulk_insert_and_stream_200k():
    db = make_db()
    total = 200_000
    for i in range(total):
        db.insert("players", {"id": i, "name": f"n{i}", "status": "new"})
    assert db.count("players") == total
    streamed = 0
    batch_sizes = set()
    for batch in db.select("players"):
        batch_sizes.add(len(batch))
        streamed += len(batch)
    assert streamed == total
    assert batch_sizes == {1000}


# --- C3: session proxy + pool occupancy model --------------------------

ROW = {"id": 1, "name": "a", "status": "new"}


def make_pool(**config: Any) -> SimSessionPool:
    return SimSessionPool(db=make_db(), config=SimPoolConfig(**config))


def test_session_context_commits_closes_and_releases():
    pool = make_pool()

    async def run():
        async with pool.session() as session:
            assert await session.execute("insert", "players", row=ROW) == 1
            await session.commit()
            await session.close()
        assert pool.pool.checked_out == 0

    asyncio.run(run())
    assert pool._db.count("players") == 1


def test_session_releases_occupancy_on_exception():
    pool = make_pool()

    async def run():
        with pytest.raises(RuntimeError, match="boom"):
            async with pool.session():
                raise RuntimeError("boom")
        assert pool.pool.checked_out == 0

    asyncio.run(run())


def test_pool_exhaustion_raises_timeout_then_recovers():
    pool = make_pool(size=2, max_overflow=1, timeout_s=0.01)

    async def run():
        held = [await pool.acquire() for _ in range(3)]
        assert pool.pool.checked_out == 3
        with pytest.raises(TimeoutError, match="connection timed out"):
            await pool.acquire()
        await held[-1].close()
        fourth = await pool.acquire()
        assert pool.pool.checked_out == 3
        for session in (*held[:-1], fourth):
            await session.close()
        assert pool.pool.checked_out == 0

    asyncio.run(run())


def test_session_execute_ops_hit_simdb_with_rowcounts():
    pool = make_pool()

    async def run():
        async with pool.session() as session:
            assert await session.execute("insert", "players", row=ROW) == 1
            assert (
                await session.execute(
                    "upsert", "players", row={"id": 1, "name": "a", "status": "up"}
                )
                == 2
            )
            assert (
                await session.execute(
                    "insert_ignore",
                    "players",
                    row={"id": 9, "name": "a", "status": "x"},
                )
                == 0
            )
            assert await session.execute("count", "players") == 1
            batches = await session.execute("select", "players")
            assert [[r["status"] for r in batch] for batch in batches] == [["up"]]
            assert (
                await session.execute(
                    "delete_limit", "players", where=lambda r: True, limit=10
                )
                == 1
            )

    asyncio.run(run())
    assert pool._db.count("players") == 0


def test_session_rejects_unknown_and_closed_ops():
    pool = make_pool()

    async def run():
        async with pool.session() as session:
            with pytest.raises(ValueError, match="unsupported op"):
                await session.execute("drop_table", "players")
        with pytest.raises(Exception, match="closed"):
            await session.execute("count", "players")

    asyncio.run(run())


def test_concurrent_sessions_within_limit_work():
    pool = make_pool(size=3, max_overflow=0)

    async def run():
        async def insert_one(i: int):
            async with pool.session() as session:
                return await session.execute(
                    "insert",
                    "players",
                    row={"id": i, "name": f"n{i}", "status": "new"},
                )

        rowcounts = list(await asyncio.gather(*(insert_one(i) for i in range(3))))
        assert rowcounts == [1, 1, 1]
        assert pool.pool.checked_out == 0

    asyncio.run(run())
    assert pool._db.count("players") == 3


def test_pool_timeout_pct_forces_checkout_timeout_deterministically():
    pool = SimSessionPool(
        db=make_db(),
        config=SimPoolConfig(),
        faults=DbFaultConfig(pool_timeout_pct=100.0),
        seed=7,
    )

    async def run():
        for _ in range(3):
            with pytest.raises(TimeoutError, match="connection timed out"):
                await pool.acquire()
        assert pool.pool.checked_out == 0

    asyncio.run(run())
