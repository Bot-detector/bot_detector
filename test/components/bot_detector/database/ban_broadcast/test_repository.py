"""Lock the SQL semantics that the legacy job got wrong.

The repository owns raw TextClauses; these tests pin the predicates that
keep the announced set (SELECT pages) and the applied set (batched PK
UPDATEs) consistent - applied is a subset of announced by construction,
so the UPDATE must never re-vet with its own predicate drift.
"""

import pytest
from bot_detector.database.ban_broadcast.repository import (
    REAL_PLAYER_LABEL,
    _sql_apply_bot_bans,
    _sql_count_banned_no_data,
    _sql_count_banned_players,
    _sql_count_banned_real_players,
    _sql_select_banned_bots_page,
)

PENDING_PREDICATES = [
    "possible_ban = 1",
    "confirmed_ban = 0",
]


def test_select_pages_by_id_cursor():
    """Pagination must be deterministic and bounded: id cursor + LIMIT,
    ordered by id (backfill idiom), so the read streams instead of
    materializing every pending bot in one result set."""
    sql = _sql_select_banned_bots_page().text
    for clause in [
        "pl.id > :player_id",
        "ORDER BY pl.id",
        "LIMIT :limit",
        "pl.id AS player_id",
    ]:
        assert clause in sql, f"lost: {clause}"


def test_select_pages_carry_pending_predicates():
    sql = _sql_select_banned_bots_page().text
    for predicate in PENDING_PREDICATES + [
        "pl.name IS NOT NULL",
        "JSON_EXTRACT(pr.predictions, '$.\"Real_Player\"') < 0.5",
    ]:
        assert predicate in sql, f"SELECT lost predicate: {predicate}"


def test_apply_bans_is_pk_only_and_targets_unapplied():
    """Lock strategy: the UPDATE is single-table by PK (no JOIN, no
    JSON evaluation - the ids were vetted by the SELECT), and
    confirmed_ban = 0 keeps rowcount equal to rows changed per batch."""
    sql = _sql_apply_bot_bans().text
    assert "confirmed_ban = 0" in sql
    assert "id IN :ids" in sql
    assert "JOIN" not in sql
    assert "JSON_EXTRACT" not in sql


def test_apply_takes_expanding_id_param():
    params = _sql_apply_bot_bans()._bindparams
    assert set(params) == {"ids"}
    assert params["ids"].expanding


def test_count_queries_cover_pending_state():
    for sql in (
        _sql_count_banned_players(),
        _sql_count_banned_real_players(),
        _sql_count_banned_no_data(),
    ):
        for predicate in PENDING_PREDICATES:
            assert predicate in sql.text


def test_real_player_label_matches_writer():
    """worker_ml stores 'Real_Player'; legacy queried 'Real_player' and only
    worked because MySQL collation is case-insensitive."""
    assert REAL_PLAYER_LABEL == "Real_Player"
    assert ":real_player_label" in _sql_count_banned_real_players().text


def test_no_data_count_uses_not_exists():
    """highscore_data_latest.player_id is NOT NULL + PK, so NOT EXISTS is
    safe and short-circuits on the PK (NOT IN materializes the subquery)."""
    assert "NOT EXISTS" in _sql_count_banned_no_data().text
    assert "NOT IN" not in _sql_count_banned_no_data().text


@pytest.mark.parametrize(
    "factory",
    [
        _sql_count_banned_players,
        _sql_count_banned_real_players,
        _sql_count_banned_no_data,
        _sql_select_banned_bots_page,
        _sql_apply_bot_bans,
    ],
)
def test_statements_use_single_quoted_literals(factory):
    """Double-quoted literals break under ANSI_QUOTES sql_mode (legacy used
    "Real_player"); bound params are the only quoted values allowed. Double
    quotes inside single-quoted literals (JSON path keys) are fine."""
    import re

    sql = factory().text
    stripped = re.sub(r"'(?:[^']|'')*'", "''", sql)
    assert '"' not in stripped


def test_select_banned_bots_paginates_until_empty():
    """The cursor loop must keep paging until a page comes back short/
    empty, aggregating pages into one bot list."""
    from unittest.mock import AsyncMock, MagicMock

    from bot_detector.database.ban_broadcast.repository import BanBroadcastRepo

    session = AsyncMock()

    def _page(ids: list[int]):
        result = MagicMock()
        result.mappings.return_value.all.return_value = [
            {"player_id": pid, "name": f"bot{pid}", "prediction": "vanilla"}
            for pid in ids
        ]
        return result

    session.execute = AsyncMock(
        side_effect=[_page([1, 2, 3]), _page([4, 5]), _page([])]
    )

    import asyncio

    bots = asyncio.run(
        BanBroadcastRepo().select_banned_bots(async_session=session, batch_size=3)
    )

    assert [b.player_id for b in bots] == [1, 2, 3, 4, 5]
    # first page cursor=0, second cursor=3, third cursor=5
    first = session.execute.await_args_list[0].kwargs["params"]
    second = session.execute.await_args_list[1].kwargs["params"]
    assert first == {"player_id": 0, "limit": 3}
    assert second == {"player_id": 3, "limit": 3}
