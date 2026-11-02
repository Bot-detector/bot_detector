import pytest
from bot_detector.event_queue.structs import (
    ACTIVITY_NAME_TO_FIELD,
    HighScoreStruct,
    map_highscore_keys,
)

SKILL_FIELDS = {
    "attack",
    "defence",
    "strength",
    "hitpoints",
    "ranged",
    "prayer",
    "magic",
    "cooking",
    "woodcutting",
    "fletching",
    "fishing",
    "firemaking",
    "crafting",
    "smithing",
    "mining",
    "herblore",
    "agility",
    "thieving",
    "slayer",
    "farming",
    "runecraft",
    "hunter",
    "construction",
}


def test_maps_jagex_activity_names_to_struct_fields():
    data = {
        "Abyssal Sire": 1200,
        "LMS - Rank": 2500,
        "Soul Wars Zeal": 9000,
        "Clue Scrolls (all)": 700,
        "Chambers Of Xeric: Challenge Mode": 42,
        "Kree'Arra": 500,
        "Vet'ion": 300,
        "Phosani's Nightmare": 100,
        "Theatre of Blood: Hard Mode": 60,
        "Tombs of Amascut: Expert Mode": 20,
        "TzKal-Zuk": 10,
        "TzTok-Jad": 90,
    }

    mapped = map_highscore_keys(data)

    assert mapped == {
        "abyssal_sire": 1200,
        "lms_rank": 2500,
        "soul_wars_zeal": 9000,
        "cs_all": 700,
        "chambers_of_xeric_challenge_mode": 42,
        "kreearra": 500,
        "vetion": 300,
        "phosanis_nightmare": 100,
        "theatre_of_blood_hard": 60,
        "tombs_of_amascut_expert": 20,
        "tzkal_zuk": 10,
        "tztok_jad": 90,
    }


def test_maps_skill_names_with_lowercase():
    data = {"Runecraft": 5_000_000, "Attack": 13_000_000, "Hunter": 2_000_000}

    mapped = map_highscore_keys(data)

    assert mapped == {
        "runecraft": 5_000_000,
        "attack": 13_000_000,
        "hunter": 2_000_000,
    }


def test_removes_none_values():
    data = {"Attack": None, "Abyssal Sire": 1}

    mapped = map_highscore_keys(data)

    assert mapped == {"abyssal_sire": 1}


def test_strips_surrounding_whitespace():
    data = {" Abyssal Sire ": 7}

    mapped = map_highscore_keys(data)

    assert mapped == {"abyssal_sire": 7}


def test_passes_through_unknown_names_lowercased():
    data = {"Rifts Closed": 33, "PvP Arena - Rank": 5}

    mapped = map_highscore_keys(data)

    assert mapped == {"rifts closed": 33, "pvp arena - rank": 5}


def test_keeps_already_mapped_field_names():
    data = {"abyssal_sire": 3, "runecraft": 4}

    mapped = map_highscore_keys(data)

    assert mapped == {"abyssal_sire": 3, "runecraft": 4}


def test_mapped_keys_validate_into_highscore_struct():
    data = {
        "Runecraft": 5_000_000,
        "Abyssal Sire": 1200,
        "Barrows Chests": 5000,
        "Soul Wars Zeal": 9000,
        "LMS - Rank": 2500,
        "Clue Scrolls (all)": 700,
    }

    hs = HighScoreStruct.model_validate(map_highscore_keys(data))

    assert hs.runecraft == 5_000_000
    assert hs.abyssal_sire == 1200
    assert hs.barrows_chests == 5000
    assert hs.soul_wars_zeal == 9000
    assert hs.lms_rank == 2500
    assert hs.cs_all == 700


def test_activity_map_covers_every_activity_field():
    activity_fields = set(HighScoreStruct.model_fields) - SKILL_FIELDS

    assert set(ACTIVITY_NAME_TO_FIELD.values()) == activity_fields


@pytest.mark.parametrize(
    ("jagex_name", "field"),
    [
        ("Chambers Of Xeric", "chambers_of_xeric"),
        ("Chambers of Xeric", "chambers_of_xeric"),
        ("K'ril Tsutsaroth", "kril_tsutsaroth"),
        ("The Gauntlet", "the_gauntlet"),
        ("The Corrupted Gauntlet", "the_corrupted_gauntlet"),
        ("Thermonuclear Smoke Devil", "thermonuclear_smoke_devil"),
        ("King Black Dragon", "king_black_dragon"),
    ],
)
def test_map_lookup_is_case_insensitive(jagex_name: str, field: str):
    mapped = map_highscore_keys({jagex_name: 1})

    assert mapped == {field: 1}
