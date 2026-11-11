"""Lock the SQL semantics that the legacy job got wrong.

The repository owns raw TextClauses; these tests pin the predicates that
must stay in sync between the SELECT (what gets broadcast) and the UPDATE
(what gets applied), so the announced set can never drift from the
banned set again.
"""

import pytest
from bot_detector.database.ban_broadcast.repository import (
    REAL_PLAYER_LABEL,
    _sql_apply_bot_bans,
    _sql_count_banned_no_data,
    _sql_count_banned_players,
    _sql_count_banned_real_players,
    _sql_select_banned_bots,
)

PENDING_PREDICATES = [
    "possible_ban = 1",
    "confirmed_ban = 0",
    "label_jagex = 2",
]


def test_select_and_apply_predicates_are_symmetric():
    select_sql = _sql_select_banned_bots().text
    update_sql = _sql_apply_bot_bans().text

    for predicate in PENDING_PREDICATES + [
        "pl.name IS NOT NULL",
        "JSON_EXTRACT(pr.predictions, '$.\"Real_Player\"') < 0.5",
    ]:
        assert predicate in select_sql, f"SELECT lost predicate: {predicate}"
        assert predicate in update_sql, f"UPDATE lost predicate: {predicate}"


def test_apply_bans_targets_only_unapplied_bans():
    """Legacy bug: the UPDATE omitted confirmed_ban = 0, so every run
    re-matched the entire historical bot set and rowcount (feeding the
    bans_applied metric) counted bots banned by previous runs."""
    assert "confirmed_ban = 0" in _sql_apply_bot_bans().text


def test_select_excludes_null_names():
    """Players.name is nullable (no NOT NULL in 01_tables.sql); a NULL name
    would raise pydantic ValidationError in the repo and abort the run."""
    assert "pl.name IS NOT NULL" in _sql_select_banned_bots().text
    assert "pl.name IS NOT NULL" in _sql_apply_bot_bans().text


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


def test_select_is_ordered():
    """Deterministic embed ordering run-to-run (legacy pop() order was
    effectively arbitrary)."""
    assert "ORDER BY" in _sql_select_banned_bots().text


@pytest.mark.parametrize(
    "factory",
    [
        _sql_count_banned_players,
        _sql_count_banned_real_players,
        _sql_count_banned_no_data,
        _sql_select_banned_bots,
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
