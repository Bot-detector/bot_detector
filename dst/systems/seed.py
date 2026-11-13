from collections.abc import Iterable, Iterator
from typing import Any

_BASE_TS = 1_700_000_000
_GOLDEN = 0x9E3779B97F4A7C15
_M1 = 0xBF58476D1CE4E5B9
_M2 = 0x94D049BB133111EB
_MASK64 = 2**64 - 1

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

# report column salts then equipment salts (30 + index into _EQUIP_KEYS);
# ordering must match the positional reads in ``reports``
_REPORT_MIX_SALTS = (10, 12, 13, 14, 15, 16, 17, 18, 19) + tuple(
    30 + i for i in range(len(_EQUIP_KEYS))
)


def _mix(seed: int, index: int, salt: int) -> int:
    """Splitmix64-mix ``(seed, index, salt)`` into a 64-bit int.

    Counter-based mixing: cheap, replayable per seed, no hashlib on
    the hot path.
    """
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
    # splitmix64 inlined on the 1M-row hot path: identical values to
    # _mix(seed, i, salt) per salt, without 20 calls per row (the & mask
    # equals % 2**64 for all ints, negatives included)
    golden = _GOLDEN
    m1 = _M1
    m2 = _M2
    mask = _MASK64
    base_ts = _BASE_TS
    for i in range(count):
        reported = pool[i % n]
        reporter = pool[(i * 7_919 + seed) % n]
        mixed: list[int] = []
        push = mixed.append
        for salt in _REPORT_MIX_SALTS:
            x = (seed + i * golden + salt * m1) & mask
            x = ((x ^ (x >> 30)) * m1) & mask
            x = ((x ^ (x >> 27)) * m2) & mask
            push(x ^ (x >> 31))
        row: dict[str, Any] = {
            "reporter_id": reporter,
            "reported_id": reported,
            "manual_detect": mixed[0] % 2,
            "region_id": mixed[1] % 100_000,
            "x_coord": mixed[2] % 3_400,
            "y_coord": mixed[3] % 3_400,
            "z_coord": mixed[4] % 4,
            "timestamp": base_ts + mixed[5] % 2_592_000,
            "on_members_world": mixed[6] % 2,
            "on_pvp_world": mixed[7] % 2,
            "world_number": 300 + mixed[8] % 700,
        }
        for offset, key in enumerate(_EQUIP_KEYS, start=9):
            d = mixed[offset]
            row[key] = None if d % 4 == 0 else d % 32_768
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
