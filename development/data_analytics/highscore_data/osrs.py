import re
from typing import Any

import polars as pl


def _normalize(name: str) -> str:
    name = name.lower().replace("\u2019", "'").replace("'", "")
    return re.sub(r"[^a-z0-9]+", "_", name).strip("_")


# example https://secure.runescape.com/m=hiscore_oldschool/index_lite.json?player=ferrariic
SKILL_NAMES: list[str] = [
    "Attack",
    "Defence",
    "Strength",
    "Hitpoints",
    "Ranged",
    "Prayer",
    "Magic",
    "Cooking",
    "Woodcutting",
    "Fletching",
    "Fishing",
    "Firemaking",
    "Crafting",
    "Smithing",
    "Mining",
    "Herblore",
    "Agility",
    "Thieving",
    "Slayer",
    "Farming",
    "Runecraft",
    "Hunter",
    "Construction",
    "Sailing",
]
NORMALIZED_SKILL_NAMES: list[str] = [_normalize(n) for n in SKILL_NAMES]

ACTIVITY_NAMES: list[str] = [
    "Grid Points",
    "League Points",
    "Deadman Points",
    "Bounty Hunter - Hunter",
    "Bounty Hunter - Rogue",
    "Bounty Hunter (Legacy) - Hunter",
    "Bounty Hunter (Legacy) - Rogue",
    "Clue Scrolls (all)",
    "Clue Scrolls (beginner)",
    "Clue Scrolls (easy)",
    "Clue Scrolls (medium)",
    "Clue Scrolls (hard)",
    "Clue Scrolls (elite)",
    "Clue Scrolls (master)",
    "LMS - Rank",
    "PvP Arena - Rank",
    "Soul Wars Zeal",
    "Rifts closed",
    "Colosseum Glory",
    "Collections Logged",
    "Abyssal Sire",
    "Alchemical Hydra",
    "Amoxliatl",
    "Araxxor",
    "Artio",
    "Barrows Chests",
    "Brutus",
    "Bryophyta",
    "Callisto",
    "Calvar'ion",
    "Cerberus",
    "Chambers of Xeric",
    "Chambers of Xeric: Challenge Mode",
    "Chaos Elemental",
    "Chaos Fanatic",
    "Commander Zilyana",
    "Corporeal Beast",
    "Crazy Archaeologist",
    "Dagannoth Prime",
    "Dagannoth Rex",
    "Dagannoth Supreme",
    "Deranged Archaeologist",
    "Doom of Mokhaiotl",
    "Duke Sucellus",
    "General Graardor",
    "Giant Mole",
    "Grotesque Guardians",
    "Hespori",
    "Kalphite Queen",
    "King Black Dragon",
    "Kraken",
    "Kree'Arra",
    "K'ril Tsutsaroth",
    "Lunar Chests",
    "Mimic",
    "Nex",
    "Nightmare",
    "Phosani's Nightmare",
    "Obor",
    "Phantom Muspah",
    "Sarachnis",
    "Scorpia",
    "Scurrius",
    "Shellbane Gryphon",
    "Skotizo",
    "Sol Heredit",
    "Spindel",
    "Tempoross",
    "The Gauntlet",
    "The Corrupted Gauntlet",
    "The Hueycoatl",
    "The Leviathan",
    "The Royal Titans",
    "The Whisperer",
    "Theatre of Blood",
    "Theatre of Blood: Hard Mode",
    "Thermonuclear Smoke Devil",
    "Tombs of Amascut",
    "Tombs of Amascut: Expert Mode",
    "TzKal-Zuk",
    "TzTok-Jad",
    "Vardorvis",
    "Venenatis",
    "Vet'ion",
    "Vorkath",
    "Wintertodt",
    "Yama",
    "Zalcano",
    "Zulrah",
]
NORMALIZED_ACTIVITY_NAMES: list[str] = [_normalize(n) for n in ACTIVITY_NAMES]

LOOKUP: dict[str, str] = {
    "cs_beginner": "clue_scrolls_beginner",
    "cs_easy": "clue_scrolls_easy",
    "cs_medium": "clue_scrolls_medium",
    "cs_hard": "clue_scrolls_hard",
    "cs_master": "clue_scrolls_master",
    "cs_elite": "clue_scrolls_elite",
    "cs_all": "clue_scrolls_all",
    "tombs_of_amascut_expert": "tombs_of_amascut_expert_mode",
    "theatre_of_blood_hard": "theatre_of_blood_hard_mode",
    "league": "league_points",
}


def skill_lookup(col: str) -> str:
    col = _normalize(col)
    if col in NORMALIZED_SKILL_NAMES:
        return col
    _col = LOOKUP.get(col, None)
    if _col is None:
        raise ValueError(f"Unknown skill column: [{col}] => [{_col}]")
    if _col not in NORMALIZED_SKILL_NAMES:
        raise ValueError(f"Lookup column is not a known skill: [{col}] => [{_col}]")
    return _col


def activity_lookup(col: str) -> str:
    _col = _normalize(col)
    if _col in NORMALIZED_ACTIVITY_NAMES:
        return _col
    _col = LOOKUP.get(_col, None)
    if _col is None:
        raise ValueError(f"Unknown activity column: [{col}] => [{_col}]")
    if _col not in NORMALIZED_ACTIVITY_NAMES:
        raise ValueError(f"Lookup column is not a known activity: [{col}] => [{_col}]")
    return _col


def column_name(canonical: str) -> str:
    return _normalize(canonical)


def _schema_col(name: str) -> tuple[str, Any]:
    return (column_name(name), pl.UInt32())


skills_dtype = pl.Struct({column_name(n): pl.UInt32() for n in NORMALIZED_SKILL_NAMES})
activities_dtype = pl.Struct(
    {column_name(n): pl.UInt32() for n in NORMALIZED_ACTIVITY_NAMES}
)

PARQUET_SCHEMA: dict[str, Any] = {
    "player_id": pl.UInt32(),
    "player_name": pl.Utf8(),
    "scrape_date": pl.Date(),
    **dict(_schema_col(n) for n in NORMALIZED_SKILL_NAMES),
    **dict(_schema_col(n) for n in NORMALIZED_ACTIVITY_NAMES),
}
