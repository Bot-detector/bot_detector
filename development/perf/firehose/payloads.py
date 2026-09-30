"""Deterministic ScrapedStruct payload pool for the firehose sim.

Everything (names, xp, ban flags, timestamps) comes from one seeded
RNG plus a fixed base time, so the same PayloadConfig builds
byte-identical payloads across runs. No datetime.now() anywhere: the
old pool logged the wall clock into created_at/updated_at, which made
seeded runs non-replayable.
"""

import logging
import random
from datetime import date, datetime, timedelta

import orjson
from bot_detector.event_queue.structs import ScrapedStruct
from bot_detector.structs._metadata import MetaData
from bot_detector.structs.hiscore import HighscoreBaseStruct
from bot_detector.structs.player import PlayerStruct
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

BASE_TIME = datetime(2026, 9, 29, 12, 0, 0)

OSRS_SKILLS = [
    "attack",
    "strength",
    "defence",
    "ranged",
    "prayer",
    "magic",
    "runecrafting",
    "hitpoints",
    "crafting",
    "mining",
    "smithing",
    "fishing",
    "cooking",
    "firemaking",
    "woodcutting",
    "agility",
    "herblore",
    "thieving",
    "fletching",
    "slayer",
    "farming",
    "construction",
    "hunter",
]
OSRS_ACTIVITIES = [
    "league_points",
    "bounty_hunter_hunter",
    "bounty_hunter_rogue",
    "clue_scrolls_all",
    "clue_scrolls_beginner",
    "clue_scrolls_easy",
    "clue_scrolls_medium",
    "clue_scrolls_hard",
    "clue_scrolls_elite",
    "clue_scrolls_master",
    "last_man_standing",
    "pvp_arena",
    "soul_wars_zeal",
    "rifts_closed",
    "collections_logged",
    "barbarian_assault",
    "ba_attackers",
    "ba_defenders",
    "ba_collectors",
    "ba_healers",
    "duel_tournament",
    "horde_defence",
    "giants_foundry",
    "guardians_of_the_rift",
    "tombs_of_amascut",
    "theatre_of_blood",
    "chambers_of_xeric",
    "nightmare",
    "phosani_nightmare",
    "sepulchre",
]

MAX_XP = 200_000_000
MAX_ACT = 10_000

NAME_PARTS_A = [
    "Dark",
    "Iron",
    "Silent",
    "Wild",
    "Zul",
    "Iron",
    "L33t",
    "Pure",
    "Nite",
    "Frost",
]
NAME_PARTS_B = [
    "mage",
    "knight",
    "ranger",
    "slayer",
    "Noob",
    "Gamer",
    "Bandit",
    "Wolf",
    "Boss",
    "420",
]


class PlayerFlagPcts(BaseModel):
    """Player flag probabilities (%), drawn from the seeded RNG."""

    possible_ban_pct: float = Field(default=10.0, ge=0.0, le=100.0)
    confirmed_ban_pct: float = Field(default=5.0, ge=0.0, le=100.0)
    confirmed_player_pct: float = Field(default=80.0, ge=0.0, le=100.0)
    ironman_pct: float = Field(default=20.0, ge=0.0, le=100.0)


class PayloadConfig(BaseModel):
    """Config for the simulated payload pool; seed -> same bytes."""

    seed: int = 0
    pool_size: int = Field(default=2000, ge=1)
    flags: PlayerFlagPcts = Field(default_factory=PlayerFlagPcts)
    base_time: datetime = BASE_TIME


def _hit(rng: random.Random, pct: float) -> bool:
    return rng.random() * 100.0 < pct


def build_payload_pool(config: PayloadConfig) -> list[bytes]:
    """Build the raw-JSON payload pool; deterministic for a given config."""
    rng = random.Random(config.seed)
    scrape: date = config.base_time.date()
    pool: list[bytes] = []
    for i in range(config.pool_size):
        name = f"{rng.choice(NAME_PARTS_A)}{rng.choice(NAME_PARTS_B)}{i}"
        skills = {s: rng.randint(1, MAX_XP) for s in OSRS_SKILLS}
        skills["total"] = sum(skills.values())
        activities = {a: rng.randint(0, MAX_ACT) for a in OSRS_ACTIVITIES}
        msg = ScrapedStruct(
            metadata=MetaData(version=0, source="sim"),
            player_data=PlayerStruct(
                id=i,
                name=name,
                created_at=config.base_time - timedelta(days=rng.randint(1, 2000)),
                updated_at=config.base_time,
                possible_ban=_hit(rng, config.flags.possible_ban_pct),
                confirmed_ban=_hit(rng, config.flags.confirmed_ban_pct),
                confirmed_player=_hit(rng, config.flags.confirmed_player_pct),
                label_id=rng.randint(0, 40),
                label_jagex=rng.randint(0, 5),
                ironman=_hit(rng, config.flags.ironman_pct),
            ),
            highscore_data=HighscoreBaseStruct(
                player_id=i,
                scrape_date=scrape,
                time_to_live=scrape + timedelta(days=30),
                skills=skills,
                activities=activities,
            ),
        )
        pool.append(orjson.dumps(msg.model_dump()))
    sizes = [len(p) for p in pool]
    logger.info(
        f"sim payload pool ready: {config.pool_size} msgs, "
        f"avg={sum(sizes) / config.pool_size / 1024:.1f}KiB"
    )
    return pool
