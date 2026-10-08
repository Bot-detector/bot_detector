"""Tests for dst.systems.seed row generators."""

import time
from itertools import islice

from dst.systems.seed import hiscores, players, reports

PLAYER_COLUMNS = {
    "id",
    "name",
    "updated_at",
    "possible_ban",
    "confirmed_ban",
    "confirmed_player",
    "label_id",
    "label_jagex",
}

REPORT_COLUMNS = {
    "reporter_id",
    "reported_id",
    "manual_detect",
    "equip_head_id",
    "equip_amulet_id",
    "equip_torso_id",
    "equip_legs_id",
    "equip_boots_id",
    "equip_cape_id",
    "equip_hands_id",
    "equip_weapon_id",
    "equip_shield_id",
    "region_id",
    "x_coord",
    "y_coord",
    "z_coord",
    "timestamp",
    "on_members_world",
    "on_pvp_world",
    "world_number",
}

HISCORE_COLUMNS = {
    "player_id",
    "scrape_date",
    "time_to_live",
    "skills",
    "activities",
}


def test_players_deterministic():
    assert list(players(50, seed=7)) == list(players(50, seed=7))


def test_players_seed_changes_rows():
    assert list(players(20, seed=1)) != list(players(20, seed=2))


def test_reports_deterministic():
    a = list(reports(50, player_ids=range(10), seed=3))
    b = list(reports(50, player_ids=range(10), seed=3))
    assert a == b


def test_hiscores_deterministic_per_player():
    a = list(hiscores(player_ids=range(20), seed=5))
    b = list(hiscores(player_ids=range(20), seed=5))
    assert a == b
    assert a[3] == next(hiscores(player_ids=[3], seed=5))


def test_players_lazy():
    gen = players(1_000_000, seed=0)
    rows = list(islice(gen, 5))
    assert len(rows) == 5
    assert rows[0]["name"] == "player_0"
    assert rows[4]["name"] == "player_4"


def test_reports_lazy():
    gen = reports(1_000_000, player_ids=range(100), seed=0)
    rows = list(islice(gen, 5))
    assert len(rows) == 5


def test_player_columns_match_insert_path():
    row = next(players(1, seed=0))
    assert set(row) == PLAYER_COLUMNS


def test_report_columns_match_insert_path():
    row = next(reports(1, player_ids=[1], seed=0))
    assert set(row) == REPORT_COLUMNS


def test_hiscore_columns_match_upsert_path():
    row = next(hiscores(player_ids=[1], seed=0))
    assert set(row) == HISCORE_COLUMNS


def test_report_player_ids_cycle():
    rows = list(reports(5, player_ids=[7, 9], seed=0))
    assert [row["reported_id"] for row in rows] == [7, 9, 7, 9, 7]
    assert all(row["reporter_id"] in {7, 9} for row in rows)


def test_report_values_realistic():
    row = next(reports(1, player_ids=[1], seed=0))
    assert 0 <= row["region_id"] <= 100_000
    assert 300 <= row["world_number"] <= 1_000
    assert row["manual_detect"] in {0, 1}
    assert isinstance(row["timestamp"], int)
    for key in REPORT_COLUMNS:
        if key.startswith("equip_"):
            assert row[key] is None or 0 <= row[key] < 32_768


def test_players_200k_stream_under_10s():
    checksum = 0
    start = time.perf_counter()
    for row in players(200_000, seed=9):
        checksum = (checksum * 1000003 + row["id"] + len(row["name"])) % 2**64
    elapsed = time.perf_counter() - start
    assert checksum != 0
    assert elapsed < 10.0
