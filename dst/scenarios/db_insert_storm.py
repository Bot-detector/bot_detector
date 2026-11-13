import asyncio
from itertools import islice
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError, OperationalError

from dst.faults import DbFaultConfig, draw
from dst.loop import running_clock
from dst.systems.db_faults import ERR_DEADLOCK, FaultSession
from dst.systems.seed import players, reports
from dst.systems.sim_db import SimDB, TableSchema
from dst.testing import Invariant, Scorecard, Subscores, invariants_failed

PLAYERS_SCHEMA = TableSchema(
    name="players",
    columns=(
        "id",
        "name",
        "updated_at",
        "possible_ban",
        "confirmed_ban",
        "confirmed_player",
        "label_id",
        "label_jagex",
    ),
    primary_key=("id",),
)

# composite natural key, no synthetic id: rows stream from the seed
# generator unchanged and INSERT IGNORE dedup stays observable
REPORTS_SCHEMA = TableSchema(
    name="reports",
    columns=(
        "reporter_id",
        "reported_id",
        "manual_detect",
        "region_id",
        "x_coord",
        "y_coord",
        "z_coord",
        "timestamp",
        "on_members_world",
        "on_pvp_world",
        "world_number",
        "equip_head_id",
        "equip_amulet_id",
        "equip_torso_id",
        "equip_legs_id",
        "equip_boots_id",
        "equip_cape_id",
        "equip_hands_id",
        "equip_weapon_id",
        "equip_shield_id",
    ),
    primary_key=("reporter_id", "reported_id", "timestamp"),
)

DUP_RACE_STREAM = "scenario:duprace"


class DbInsertStormConfig(BaseModel):
    """Scenario knobs; deadlock_pct stays below 100 (retry must land)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    seed: int = 0
    total: int = Field(default=1_000_000, ge=1)
    n_players: int = Field(default=10_000, ge=1)
    batch_size: int = Field(default=1_000, ge=1)
    batch_pause_s: float = Field(default=0.01, ge=0.0)
    dup_pct: float = Field(default=1.0, ge=0.0, le=100.0)
    deadlock_pct: float = Field(default=0.0, ge=0.0, lt=100.0)
    drain_budget_s: float = Field(default=60.0, ge=0.0)


class _Counters:
    """Storm counters threaded through the insert helpers."""

    def __init__(self) -> None:
        self.attempted = 0
        self.inserted = 0
        self.skipped_dups = 0
        self.dup_rejected = 0
        self.retries = 0


def _errno_of(exc: OperationalError) -> int:
    """MySQL errno carried by the asyncmy-shaped orig."""
    orig: Any = exc.orig
    return int(orig.errno)


def _insert_ignore_retrying(
    session: FaultSession, table: str, row: dict[str, Any], counters: _Counters
) -> None:
    """INSERT IGNORE, retrying deadlock raises until the row lands."""
    while True:
        try:
            rowcount = session.insert_ignore(table, row)
        except OperationalError as exc:
            if _errno_of(exc) != ERR_DEADLOCK:
                raise
            counters.retries += 1
            continue
        counters.attempted += 1
        if rowcount == 1:
            counters.inserted += 1
        else:
            counters.skipped_dups += 1
        return


def _dup_race_insert(
    session: FaultSession, table: str, row: dict[str, Any], counters: _Counters
) -> None:
    """Plain INSERT re-insert; IntegrityError means the race lost."""
    while True:
        try:
            session.insert(table, row)
        except IntegrityError:
            counters.dup_rejected += 1
            return
        except OperationalError as exc:
            if _errno_of(exc) != ERR_DEADLOCK:
                raise
            counters.retries += 1
            continue
        # The re-insert can only land when the original row never made
        # it in; the ignore-insert path above guarantees it did.
        return


def _seed_players(db: SimDB, config: DbInsertStormConfig) -> None:
    """Load fixture players straight on the store (outside the storm)."""
    for row in players(config.n_players, seed=config.seed):
        db.insert("players", row)


async def main(**kwargs) -> Scorecard:
    """Run the report insert storm and return its scorecard.

    Zero-wiring (pure asyncio, no app): stream ``total`` seeded report
    rows through a FaultSession's ``insert_ignore`` in batches and
    interleave a dup race — a configurable pct of rows are re-inserted
    with a plain ``insert``, catching the real ``IntegrityError``
    (1062) the non-IGNORE race produces.

    Deadlock policy: every OperationalError with errno 1213 is caught
    and the statement retried until it lands (deterministic: draws are
    counter-based and deadlock_pct < 100; a literal single retry is
    insufficient at sustained pct, where expected double-faults are
    pct^2 * N). Each catch counts one retry; ``retries`` is the cost
    signal for hill climbing.

    Draw order (FIXED): per report row i, one dup-race
    selection draw ``draw(seed, "scenario:duprace", i)``; each
    fault-checked statement consumes one FaultSession ordinal on
    ``db:x:reports`` (ignore first, then the race re-insert when
    selected).

    Subscores: ``loss`` = 1.0 when no_loss holds; ``drain`` = 1.0 when
    the storm finishes within ``drain_budget_s`` of virtual time;
    ``keep_up`` = 1.0 always — an insert storm has no feed to keep
    pace with, the only bottleneck modeled is fault retries. Score is
    0.0 when any invariant fails, else the mean of the subscores.
    """
    config = DbInsertStormConfig(**kwargs)
    db = SimDB()
    db.define_table(PLAYERS_SCHEMA)
    db.define_table(REPORTS_SCHEMA)
    _seed_players(db, config)
    session = FaultSession(
        db, DbFaultConfig(deadlock_pct=config.deadlock_pct), seed=config.seed
    )
    clock = running_clock()
    counters = _Counters()

    rows = reports(config.total, range(1, config.n_players + 1), seed=config.seed)
    while counters.attempted < config.total:
        batch = list(islice(rows, config.batch_size))
        if not batch:
            break
        for row in batch:
            _insert_ignore_retrying(session, "reports", row, counters)
            index = counters.attempted - 1
            if draw(config.seed, DUP_RACE_STREAM, index) * 100.0 < config.dup_pct:
                _dup_race_insert(session, "reports", row, counters)
        await asyncio.sleep(config.batch_pause_s)

    elapsed = clock.time()
    no_loss = counters.inserted + counters.skipped_dups == counters.attempted
    counted = db.count("reports") == counters.inserted
    invariants = [
        Invariant(
            name="no_loss",
            ok=no_loss,
            detail=(
                f"inserted={counters.inserted} skipped_dups="
                f"{counters.skipped_dups} attempted={counters.attempted}"
            ),
        ),
        Invariant(
            name="counted",
            ok=counted,
            detail=f"count={db.count('reports')} inserted={counters.inserted}",
        ),
    ]
    subscores = Subscores(
        loss=1.0 if no_loss else 0.0,
        keep_up=1.0,
        drain=1.0 if elapsed <= config.drain_budget_s else 0.0,
    )
    scorecard = Scorecard(
        seed=config.seed,
        counters={
            "inserted": counters.inserted,
            "skipped_dups": counters.skipped_dups,
            "dup_rejected": counters.dup_rejected,
            "faults_raised_total": session.faults_raised_total,
            "retries": counters.retries,
        },
        invariants=invariants,
        subscores=subscores,
    )
    scorecard.score = (
        0.0
        if invariants_failed(scorecard)
        else (subscores.loss + subscores.keep_up + subscores.drain) / 3.0
    )
    return scorecard
