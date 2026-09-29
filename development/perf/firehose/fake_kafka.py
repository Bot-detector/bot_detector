"""Fake Kafka consumer mimicking AIOKafkaConsumerAdapter's per-message path.

Consumers block on get_one() like aiokafka's getone(). The "broker" side
pre-generates raw JSON payloads (like the players_scraped seeder) and a
producer task feeds them at a fixed rate, so the pump's cost profile
(deserialize + validate + fanout) matches the real kafka adapter.
"""

import asyncio
import logging
import random
import time
from datetime import date, datetime, timedelta

import orjson
from bot_detector.event_queue.structs import ScrapedStruct
from bot_detector.structs._metadata import MetaData
from bot_detector.structs.hiscore import HighscoreBaseStruct
from bot_detector.structs.player import PlayerStruct
from prometheus_client import Gauge
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

SIM_PRODUCED = Gauge(
    "sim_produced_total", "messages fed by the sim producer", ["group"]
)
SIM_CONSUMED = Gauge(
    "sim_consumed_total", "messages consumed from the sim feed", ["group"]
)
SIM_BACKLOG = Gauge("sim_backlog", "sim feed backlog (produced - consumed)", ["group"])

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


class FakeKafkaConsumer:
    """QueueConsumer-protocol stand-in backed by an in-process queue.

    error_every/poison_every inject failure modes into the consumed
    stream (same path the real pump sees as values):

    - error_every=N: every Nth get_one returns RuntimeError("sim kafka
      error") - a transient consumer error the route skips with a 0.5s
      backoff
    - poison_every=N: every Nth get_one returns a ValidationError
      (malformed payload that fails model validation)
    """

    def __init__(
        self,
        topic: str,
        group: str,
        rate_s: int,
        pool_size: int,
        error_every: int = 0,
        poison_every: int = 0,
    ):
        self.topic = topic
        self.group = group
        self.rate_s = rate_s
        self.error_every = error_every
        self.poison_every = poison_every
        self.errors_returned = 0
        self.poison_returned = 0
        self.produced_total = 0
        self.consumed_total = 0
        self._queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=100_000)
        self._task: asyncio.Task | None = None
        self.created = time.monotonic()
        self._g_produced = SIM_PRODUCED.labels(group=group)
        self._g_consumed = SIM_CONSUMED.labels(group=group)
        self._g_backlog = SIM_BACKLOG.labels(group=group)
        self._pool = self._build_pool(pool_size)

    def _build_pool(self, n: int) -> list[bytes]:
        pool = []
        rng = random.Random(0)
        now = datetime.now()
        for i in range(n):
            name = f"{rng.choice(NAME_PARTS_A)}{rng.choice(NAME_PARTS_B)}{i}"
            skills = {s: rng.randint(1, MAX_XP) for s in OSRS_SKILLS}
            skills["total"] = sum(skills.values())
            activities = {a: rng.randint(0, MAX_ACT) for a in OSRS_ACTIVITIES}
            scrape = date(2026, 9, 29)
            msg = ScrapedStruct(
                metadata=MetaData(version=0, source="sim"),
                player_data=PlayerStruct(
                    id=i,
                    name=name,
                    created_at=now - timedelta(days=rng.randint(1, 2000)),
                    updated_at=now,
                    possible_ban=rng.random() < 0.1,
                    confirmed_ban=rng.random() < 0.05,
                    confirmed_player=rng.random() < 0.8,
                    label_id=rng.randint(0, 40),
                    label_jagex=rng.randint(0, 5),
                    ironman=rng.random() < 0.2,
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
            f"sim payload pool ready: {n} msgs, avg={sum(sizes) / n / 1024:.1f}KiB"
        )
        return pool

    async def start(self) -> None:
        self._task = asyncio.create_task(
            self._produce(), name=f"sim-producer-{self.group}"
        )

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def get_one(self) -> BaseModel | Exception | None:
        # injected failures first: the pump/route see them as values,
        # exactly like transient kafka errors and poison payloads
        self.consumed_total += 1
        if self.error_every and self.consumed_total % self.error_every == 0:
            self.errors_returned += 1
            self._g_consumed.set(self.consumed_total)
            return RuntimeError("sim kafka error")
        if self.poison_every and self.consumed_total % self.poison_every == 0:
            self.poison_returned += 1
            self._g_consumed.set(self.consumed_total)
            try:
                return ScrapedStruct.model_validate({"nope": True})
            except ValidationError as ve:
                return ve
        raw = await self._queue.get()
        self._g_consumed.set(self.consumed_total)
        self._g_backlog.set(self.produced_total - self.consumed_total)
        # same path as AIOKafkaConsumerAdapter: value_deserializer then validate
        dct = orjson.loads(raw)
        try:
            return ScrapedStruct.model_validate(dct)
        except ValidationError as ve:
            return ve

    async def _produce(self) -> None:
        # burst per tick to hit the target rate without per-message sleeps;
        # awaiting put applies backpressure instead of crashing at maxsize
        tick_s = 0.01
        per_tick = max(1, int(self.rate_s * tick_s))
        i = 0
        n = len(self._pool)
        while True:
            t0 = time.monotonic()
            for _ in range(per_tick):
                await self._queue.put(self._pool[i % n])
                i += 1
                self.produced_total += 1
            self._g_produced.set(self.produced_total)
            self._g_backlog.set(self.produced_total - self.consumed_total)
            elapsed = time.monotonic() - t0
            delay = tick_s - elapsed
            if delay > 0:
                await asyncio.sleep(delay)
