import argparse
import asyncio
import os
import sys
from datetime import date, datetime, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from bot_detector.database.api_public.player import PlayerRepo as PublicPlayerRepo
from bot_detector.database.core import Settings, get_session_factory
from bot_detector.database.discord.repository import DiscordVerificationRepo
from bot_detector.database.discord.structs import DiscordVerificationTableStruct
from bot_detector.database.hiscore import HighscoreDataRepo
from bot_detector.database.player.repository import PlayerRepo
from bot_detector.database.prediction import PredictionLatestRepo, PredictionRepo
from bot_detector.database.report import ReportRepo
from bot_detector.structs import (
    Equipment,
    HighscoreBaseStruct,
    ParsedDetection,
    PlayerStruct,
    PredictionCreate,
)

# why: proves the raw-SQL surfaces against real MySQL semantics that mocks
# and the DST sim cannot see (generated columns, temp tables, FK rollbacks)
DEFAULT_URL = "mysql+asyncmy://root:root_bot_buster@127.0.0.1:3307/playerdata"
SMOKE_ID_BASE = 900_000
NOW = datetime.now(timezone.utc).replace(tzinfo=None)

PURGE_STATEMENTS = [
    "DELETE FROM prediction_latest WHERE player_id >= 900000",
    "DELETE FROM prediction WHERE player_id >= 900000",
    "DELETE FROM highscore_data_latest WHERE player_id >= 900000",
    "DELETE FROM highscore_data_daily WHERE player_id >= 900000",
    "DELETE FROM highscore_data_weekly WHERE player_id >= 900000",
    "DELETE FROM highscore_data_monthly WHERE player_id >= 900000",
    "DELETE FROM report_sighting WHERE reporting_id >= 900000",
    "DELETE FROM Players WHERE id >= 900000",
    "DELETE FROM DiscordVerification WHERE Discord_id LIKE 'smoke%'",
]

SEED_PLAYER_SQL = """
INSERT IGNORE INTO Players
    (id, name, created_at, updated_at, possible_ban,
     confirmed_ban, confirmed_player, label_id, label_jagex)
VALUES (:id, :name, :created_at, :updated_at, 0, 0, 1, 0, 0)
"""


async def purge(factory: async_sessionmaker[AsyncSession]) -> None:
    async with factory() as session, session.begin():
        for stmt in PURGE_STATEMENTS:
            await session.execute(sa.text(stmt))


async def seed_player(
    factory: async_sessionmaker[AsyncSession],
    player_id: int,
    name: str,
    updated_at: datetime | None,
) -> None:
    async with factory() as session, session.begin():
        await session.execute(
            sa.text(SEED_PLAYER_SQL),
            {
                "id": player_id,
                "name": name,
                "created_at": NOW,
                "updated_at": updated_at,
            },
        )


async def ensure_discord_table(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: DiscordVerificationTableStruct.__table__.create(
                sync_conn, checkfirst=True
            )
        )


async def check_prediction_atomic(factory: async_sessionmaker[AsyncSession]) -> str:
    good = PredictionCreate(
        player_id=SMOKE_ID_BASE + 1,
        model_name="smoke_model",
        prediction="Real_Player",
        confidence=0.9,
        predictions={"Real_Player": 0.9},
    )
    bad = good.model_copy(update={"player_id": SMOKE_ID_BASE + 999_999})
    await seed_player(factory, SMOKE_ID_BASE + 1, "smoke_pred_a", NOW)

    raised = False
    try:
        async with factory() as session, session.begin():
            await PredictionRepo().insert(
                async_session=session, predictions=[good, bad]
            )
            await PredictionLatestRepo().insert(
                async_session=session, predictions=[good]
            )
    except sa.exc.IntegrityError:
        raised = True
    if not raised:
        raise AssertionError("FK failure did not raise IntegrityError")

    async with factory() as session:
        leaked = await session.scalar(
            sa.text(
                f"SELECT COUNT(*) FROM prediction WHERE player_id = {SMOKE_ID_BASE + 1}"
            )
        )
    if leaked != 0:
        raise AssertionError(f"rollback leaked {leaked} prediction rows")

    async with factory() as session, session.begin():
        await PredictionRepo().insert(async_session=session, predictions=[good])
        await PredictionLatestRepo().insert(async_session=session, predictions=[good])
    async with factory() as session:
        count = await session.scalar(
            sa.text(
                f"SELECT COUNT(*) FROM prediction WHERE player_id = {SMOKE_ID_BASE + 1}"
            )
        )
    if count != 1:
        raise AssertionError(f"happy path landed {count} rows, expected 1")
    return "FK failure rolls back the whole batch, happy path lands 1"


async def check_player_temp_table_20k(factory: async_sessionmaker[AsyncSession]) -> str:
    # 20k rows exceed the 16MB default MEMORY ceiling; InnoDB must take it
    total = 20_000
    first_id = SMOKE_ID_BASE + 100_000
    rows = [
        {
            "id": first_id + i,
            "name": f"smoke_bulk_{i}",
            "created_at": NOW,
            "updated_at": None,
        }
        for i in range(total)
    ]
    async with factory() as session, session.begin():
        await session.execute(sa.text(SEED_PLAYER_SQL), rows)

    players = [
        PlayerStruct(id=row["id"], name=row["name"], created_at=NOW, updated_at=NOW)
        for row in rows
    ]
    async with factory() as session, session.begin():
        await PlayerRepo().update_many_players(
            async_session=session, players_data=players
        )

    async with factory() as session:
        updated = await session.scalar(
            sa.text(
                "SELECT COUNT(*) FROM Players "
                f"WHERE id >= {first_id} AND updated_at IS NOT NULL"
            )
        )
    if updated != total:
        raise AssertionError(f"updated {updated}/{total} players via temp table")
    return f"{total} players through the temp-table path, all updated"


def _highscore_batch(scrape_date: date) -> list[HighscoreBaseStruct]:
    return [
        HighscoreBaseStruct(
            player_id=SMOKE_ID_BASE + 500 + i,
            scrape_date=scrape_date,
            time_to_live=scrape_date,
            skills={"attack": i},
            activities={},
        )
        for i in range(500)
    ]


async def check_highscore_upserts(factory: async_sessionmaker[AsyncSession]) -> str:
    batch = _highscore_batch(NOW.date())
    repo = HighscoreDataRepo()
    for _ in range(2):
        async with factory() as session, session.begin():
            await repo.insert_highscore_many(
                async_session=session, highscore_data=batch
            )

    async with factory() as session:
        for table in (
            "highscore_data_latest",
            "highscore_data_daily",
            "highscore_data_weekly",
            "highscore_data_monthly",
        ):
            count = await session.scalar(
                sa.text(
                    f"SELECT COUNT(*) FROM {table} "
                    f"WHERE player_id >= {SMOKE_ID_BASE + 500}"
                )
            )
            if count != 500:
                raise AssertionError(f"{table}: {count} rows, expected 500")
    return "double insert stays at 500 rows in all 4 partitions"


def _smoke_detection(ts: int) -> ParsedDetection:
    return ParsedDetection(
        region_id=1,
        x_coord=3200,
        y_coord=3200,
        z_coord=0,
        ts=ts,
        manual_detect=1,
        on_members_world=0,
        on_pvp_world=0,
        world_number=301,
        equipment=Equipment(equip_head_id=10),
        equip_ge_value=0,
        reporter_id=SMOKE_ID_BASE + 900,
        reported_id=SMOKE_ID_BASE + 901,
    )


async def check_report_sighting_dedupe(
    factory: async_sessionmaker[AsyncSession],
) -> str:
    repo = ReportRepo()
    detections = [_smoke_detection(1_700_000_000_000 + i * 1000) for i in range(2)]
    for _ in range(2):
        async with factory() as session, session.begin():
            await repo.insert(async_session=session, reports=detections)

    async with factory() as session:
        count = await session.scalar(
            sa.text(
                "SELECT COUNT(*) FROM report_sighting "
                f"WHERE reporting_id = {SMOKE_ID_BASE + 900} "
                f"AND reported_id = {SMOKE_ID_BASE + 901}"
            )
        )
    if count != 1:
        raise AssertionError(f"sighting duplicated: {count} rows, expected 1")
    return "double insert dedupes to one sighting"


async def check_report_score_expanding(
    factory: async_sessionmaker[AsyncSession],
) -> str:
    await seed_player(factory, SMOKE_ID_BASE + 900, "smoke_voter_1", NOW)
    await seed_player(factory, SMOKE_ID_BASE + 901, "smoke_subject_1", NOW)
    async with factory() as session, session.begin():
        await ReportRepo().insert(
            async_session=session, reports=[_smoke_detection(1_700_000_000_000)]
        )
    async with factory() as session:
        repo = PublicPlayerRepo(session)
        empty = await repo.get_report_score(())
        rows = await repo.get_report_score(("smoke_voter_1", "smoke_voter_2"))
    if empty != []:
        raise AssertionError("empty name list did not return []")
    if len(rows) < 1:
        raise AssertionError("no score rows for known voter names")
    return "empty tuple yields [], populated tuple yields rows"


async def check_set_primary_rsn_miss(
    factory: async_sessionmaker[AsyncSession],
) -> str:
    async with factory() as session, session.begin():
        await session.execute(
            sa.text(
                """
                INSERT IGNORE INTO DiscordVerification
                    (Discord_id, Player_id, Code, primary_rsn,
                     verified_status, token_used, created_at, updated_at)
                VALUES ('smoke_d1', :pid, 'code', :primary, 1, 0, :now, :now)
                """
            ),
            [
                {"pid": SMOKE_ID_BASE + 1, "primary": 1, "now": NOW},
                {"pid": SMOKE_ID_BASE + 2, "primary": 0, "now": NOW},
            ],
        )

    repo = DiscordVerificationRepo()

    async def primaries() -> list[int]:
        async with factory() as session:
            rows = await session.scalars(
                sa.text(
                    "SELECT Player_id FROM DiscordVerification "
                    "WHERE Discord_id = 'smoke_d1' AND primary_rsn = 1"
                )
            )
        return list(rows)

    async with factory() as session:
        missed = await repo.set_primary_rsn(
            async_session=session,
            discord_id="smoke_d1",
            player_id=SMOKE_ID_BASE + 999_999,
            is_primary=True,
        )
    if missed is not False:
        raise AssertionError("miss did not return False")
    if await primaries() != [SMOKE_ID_BASE + 1]:
        raise AssertionError("miss wiped or moved the existing primary flag")

    async with factory() as session:
        flipped = await repo.set_primary_rsn(
            async_session=session,
            discord_id="smoke_d1",
            player_id=SMOKE_ID_BASE + 2,
            is_primary=True,
        )
    if flipped is not True:
        raise AssertionError("flip did not return True")
    if await primaries() != [SMOKE_ID_BASE + 2]:
        raise AssertionError("flip did not leave exactly the new primary")
    return "miss keeps old primary; flip moves exactly one flag"


async def check_engine_connectivity(url: str) -> str:
    settings = Settings(DATABASE_URL=url)
    factory, engine = get_session_factory(SETTINGS=settings)
    async with factory() as session:
        one = await session.scalar(sa.text("SELECT 1"))
    await engine.dispose()
    if one != 1:
        raise AssertionError(f"SELECT 1 returned {one!r}")
    return "get_session_factory connects and pings"


CHECKS = [
    ("prediction_atomicity", check_prediction_atomic),
    ("player_temp_table_20k", check_player_temp_table_20k),
    ("highscore_upserts", check_highscore_upserts),
    ("report_sighting_dedupe", check_report_sighting_dedupe),
    ("report_score_expanding", check_report_score_expanding),
    ("set_primary_rsn_miss", check_set_primary_rsn_miss),
]


async def run_all(url: str) -> int:
    engine = create_async_engine(url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    results: list[tuple[str, str | None]] = []

    await ensure_discord_table(engine)
    await purge(factory)
    for name, check in CHECKS:
        try:
            detail = await check(factory)
            results.append((name, None))
            print(f"PASS  {name}: {detail}")
        except Exception as exc:
            results.append((name, str(exc)))
            print(f"FAIL  {name}: {exc}")
    try:
        await check_engine_connectivity(url)
        results.append(("engine_connectivity", None))
        print("PASS  engine_connectivity: get_session_factory connects and pings")
    except Exception as exc:
        results.append(("engine_connectivity", str(exc)))
        print(f"FAIL  engine_connectivity: {exc}")

    await purge(factory)
    await engine.dispose()

    failed = [name for name, detail in results if detail is not None]
    print(f"\nsmoke: {len(results) - len(failed)}/{len(results)} passed")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Real-MySQL smoke for the database brick"
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("SMOKE_DATABASE_URL", DEFAULT_URL),
        help="asyncmy DSN; defaults to SMOKE_DATABASE_URL or the compose mysql",
    )
    args = parser.parse_args()
    return asyncio.run(run_all(args.url))


if __name__ == "__main__":
    sys.exit(main())
