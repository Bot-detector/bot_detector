"""Seeded row generators for SimDB seed data (spec §5.3, task C2).

Column sets mirror the product repos' insert bind params so rows feed
``test/dst/systems/sim_db.py`` unchanged. Values derive from
``(seed, row index)`` via splitmix64 mixing — counter-based, cheap,
replayable (spec §4.1), no hashlib on the hot path.
"""

from collections.abc import Iterable, Iterator
from typing import Any

_BASE_TS = 1_700_000_000
_GOLDEN = 0x9E3779B97F4A7C15
_M1 = 0xBF58476D1CE4E5B9
_M2 = 0x94D049BB133111EB

_SKILLS = (
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
    "runecrafting",
    "hunter",
    "construction",
)

_EQUIP_KEYS = (
    "equip_head_id",
    "equip_amulet_id",
    "equip_torso_id",
    "equip_legs_id",
    "equip_boots_id",
    "equip_cape_id",
    "equip_hands_id",
    "equip_weapon_id",
    "equip_shield_id",
)


def _mix(seed: int, index: int, salt: int) -> int:
    """Splitmix64-mix ``(seed, index, salt)`` into a 64-bit int."""
    x = (seed + index * _GOLDEN + salt * _M1) % 2**64
    x = ((x ^ (x >> 30)) * _M1) % 2**64
    x = ((x ^ (x >> 27)) * _M2) % 2**64
    return x ^ (x >> 31)


def _u01(seed: int, index: int, salt: int) -> float:
    """Uniform float in [0, 1) for one (seed, index, salt) draw."""
    return _mix(seed, index, salt) / 2**64


def players(count: int, seed: int = 0) -> Iterator[dict[str, Any]]:
    """Yield ``count`` player rows matching the player insert path.

    Columns mirror ``PlayerRepo._insert_temp_player`` (components/
    bot_detector/database/player/repository.py:85), explicit ``id``
    included.

    Args:
        count: Number of rows to yield.
        seed: Run-level seed everything derives from.

    Yields:
        One player row dict per call to ``next``.
    """
    for i in range(count):
        yield {
            "id": i + 1,
            "name": f"player_{i}",
            "updated_at": _BASE_TS + _mix(seed, i, 1) % 2_592_000,
            "possible_ban": _mix(seed, i, 2) % 100 < 5,
            "confirmed_ban": _mix(seed, i, 3) % 100 < 2,
            "confirmed_player": _mix(seed, i, 4) % 100 >= 40,
            "label_id": _mix(seed, i, 5) % 10,
            "label_jagex": _mix(seed, i, 6) % 100,
        }


def reports(
    count: int, player_ids: Iterable[int], seed: int = 0
) -> Iterator[dict[str, Any]]:
    """Yield ``count`` report rows matching the report insert path.

    Columns mirror ``ReportRepo._insert_temp_report`` bind params
    (components/bot_detector/database/report/repository.py:87), the
    flattened-equipment + epoch-``timestamp`` shape produced by
    ``_parse_reports``. Reported ids cycle ``player_ids``; reporters
    draw from the same pool.

    Args:
        count: Number of rows to yield.
        player_ids: Pool of existing player ids to sight.
        seed: Run-level seed everything derives from.

    Yields:
        One report row dict per call to ``next``.

    Raises:
        ValueError: If ``player_ids`` is empty.
    """
    pool = list(player_ids)
    if not pool:
        raise ValueError("player_ids must not be empty")
    n = len(pool)
    for i in range(count):
        reported = pool[i % n]
        reporter = pool[(i * 7_919 + seed) % n]
        row: dict[str, Any] = {
            "reporter_id": reporter,
            "reported_id": reported,
            "manual_detect": _mix(seed, i, 10) % 2,
            "region_id": _mix(seed, i, 12) % 100_000,
            "x_coord": _mix(seed, i, 13) % 3_400,
            "y_coord": _mix(seed, i, 14) % 3_400,
            "z_coord": _mix(seed, i, 15) % 4,
            "timestamp": _BASE_TS + _mix(seed, i, 16) % 2_592_000,
            "on_members_world": _mix(seed, i, 17) % 2,
            "on_pvp_world": _mix(seed, i, 18) % 2,
            "world_number": 300 + _mix(seed, i, 19) % 700,
        }
        for salt, key in enumerate(_EQUIP_KEYS):
            draw = _mix(seed, i, 30 + salt)
            row[key] = None if draw % 4 == 0 else draw % 32_768
        yield row


def hiscores(player_ids: Iterable[int], seed: int = 0) -> Iterator[dict[str, Any]]:
    """Yield one hiscore row per player id, deterministic per player.

    Columns mirror the ``HighscoreDataRepo`` temp insert / upsert via
    ``HighscoreBaseStruct.model_dump`` (components/bot_detector/
    database/hiscore/repository.py:39,193); skill values are ints.

    Args:
        player_ids: Existing player ids to seed rows for.
        seed: Run-level seed everything derives from.

    Yields:
        One hiscore row dict per player id, in input order.
    """
    for player_id in player_ids:
        skills = {
            skill: 1 + _mix(seed, player_id, salt + 1) % 200_000_000
            for salt, skill in enumerate(_SKILLS)
        }
        activities = {
            f"activity_{salt}": _mix(seed, player_id, 100 + salt) % 10_000
            for salt in range(3)
        }
        scrape = _BASE_TS + _mix(seed, player_id, 200) % 2_592_000
        yield {
            "player_id": player_id,
            "scrape_date": scrape,
            "time_to_live": scrape + 30 * 86_400,
            "skills": skills,
            "activities": activities,
        }
