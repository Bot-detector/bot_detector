from typing import Any

# lowercase jagex activity display name -> HighScoreStruct / InputData field
ACTIVITY_NAME_TO_FIELD: dict[str, str] = {
    # minigames & competitive
    "clue scrolls (all)": "cs_all",
    "clue scrolls (beginner)": "cs_beginner",
    "clue scrolls (easy)": "cs_easy",
    "clue scrolls (medium)": "cs_medium",
    "clue scrolls (hard)": "cs_hard",
    "clue scrolls (elite)": "cs_elite",
    "clue scrolls (master)": "cs_master",
    "lms - rank": "lms_rank",
    "soul wars zeal": "soul_wars_zeal",
    # bosses
    "abyssal sire": "abyssal_sire",
    "alchemical hydra": "alchemical_hydra",
    "barrows chests": "barrows_chests",
    "bryophyta": "bryophyta",
    "callisto": "callisto",
    "cerberus": "cerberus",
    "chambers of xeric": "chambers_of_xeric",
    "chambers of xeric: challenge mode": "chambers_of_xeric_challenge_mode",
    "chaos elemental": "chaos_elemental",
    "chaos fanatic": "chaos_fanatic",
    "commander zilyana": "commander_zilyana",
    "corporeal beast": "corporeal_beast",
    "crazy archaeologist": "crazy_archaeologist",
    "dagannoth prime": "dagannoth_prime",
    "dagannoth rex": "dagannoth_rex",
    "dagannoth supreme": "dagannoth_supreme",
    "deranged archaeologist": "deranged_archaeologist",
    "general graardor": "general_graardor",
    "giant mole": "giant_mole",
    "grotesque guardians": "grotesque_guardians",
    "hespori": "hespori",
    "kalphite queen": "kalphite_queen",
    "king black dragon": "king_black_dragon",
    "kraken": "kraken",
    "kree'arra": "kreearra",
    "k'ril tsutsaroth": "kril_tsutsaroth",
    "mimic": "mimic",
    "nex": "nex",
    "nightmare": "nightmare",
    "phosani's nightmare": "phosanis_nightmare",
    "obor": "obor",
    "sarachnis": "sarachnis",
    "scorpia": "scorpia",
    "skotizo": "skotizo",
    "tempoross": "tempoross",
    "the gauntlet": "the_gauntlet",
    "the corrupted gauntlet": "the_corrupted_gauntlet",
    "theatre of blood": "theatre_of_blood",
    "theatre of blood: hard mode": "theatre_of_blood_hard",
    "thermonuclear smoke devil": "thermonuclear_smoke_devil",
    "tombs of amascut": "tombs_of_amascut",
    "tombs of amascut: expert mode": "tombs_of_amascut_expert",
    "tzkal-zuk": "tzkal_zuk",
    "tztok-jad": "tztok_jad",
    "venenatis": "venenatis",
    "vet'ion": "vetion",
    "vorkath": "vorkath",
    "wintertodt": "wintertodt",
    "zalcano": "zalcano",
    "zulrah": "zulrah",
}


def map_highscore_keys(data: dict[str, Any]) -> dict[str, Any]:
    """Maps hiscore keys to HighScoreStruct / InputData field names.

    Args:
        - data: dict with jagex display names (or already mapped names)
        as keys and any type of values.

    Returns:
        - dict with struct-compatible field names and no None values.
        Unknown names pass through lowercased and are ignored by the models.
    """
    mapped: dict[str, Any] = {}
    for name, value in data.items():
        if value is None:
            continue
        key = name.strip().lower()
        mapped[ACTIVITY_NAME_TO_FIELD.get(key, key)] = value
    return mapped
