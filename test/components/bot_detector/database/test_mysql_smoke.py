import os
from datetime import datetime, timezone

import pytest
import pytest_asyncio
import sqlalchemy as sqla
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
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

SMOKE_URL = os.environ.get("SMOKE_DATABASE_URL", "")

# real-MySQL smoke tier: skipped unless pointed at a disposable database,
# e.g. the compose mysql service (host port 3307) after initdb applied schema
pytestmark = pytest.mark.skipif(
    SMOKE_URL == "",
    reason="set SMOKE_DATABASE_URL=mysql+asyncmy://... to run db smoke tests",
)

NOW = datetime.now(timezone.utc).replace(tzinfo=None)
SMOKE_ID_BASE = 900_000


@pytest_asyncio.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(SMOKE_URL, pool_pre_ping=True)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def purge_smoke_rows(session_factory: async_sessionmaker[AsyncSession]):
    yield
    async with session_factory() as session, session.begin():
        for table in ("prediction_latest", "prediction"):
            await session.execute(
                sqla.text(f"DELETE FROM {table} WHERE player_id >= {SMOKE_ID_BASE}")
            )
        for table, column in (
            ("highscore_data_latest", "player_id"),
            ("highscore_data_daily", "player_id"),
            ("highscore_data_weekly", "player_id"),
            ("highscore_data_monthly", "player_id"),
            ("Players", "id"),
        ):
            await session.execute(
                sqla.text(f"DELETE FROM {table} WHERE {column} >= {SMOKE_ID_BASE}")
            )
        await session.execute(
            sqla.text("DELETE FROM report_sighting WHERE reporting_id >= 900000")
        )
        await session.execute(
            sqla.text("DELETE FROM DiscordVerification WHERE Discord_id LIKE 'smoke%'")
        )


async def _seed_player(
    session_factory: async_sessionmaker[AsyncSession],
    player_id: int,
    name: str,
    updated_at: datetime | None,
) -> None:
    async with session_factory() as session, session.begin():
        await session.execute(
            sqla.text(
                """
                INSERT IGNORE INTO Players
                    (id, name, created_at, updated_at, possible_ban,
                     confirmed_ban, confirmed_player, label_id, label_jagex)
                VALUES (:id, :name, :created_at, :updated_at, 0, 0, 1, 0, 0)
                """
            ),
            {
                "id": player_id,
                "name": name,
                "created_at": NOW,
                "updated_at": updated_at,
            },
        )


@pytest.mark.asyncio
async def test_prediction_batch_is_atomic_on_failure(
    session_factory: async_sessionmaker[AsyncSession],
):
    good = PredictionCreate(
        player_id=SMOKE_ID_BASE + 1,
        model_name="smoke_model",
        prediction="Real_Player",
        confidence=0.9,
        predictions={"Real_Player": 0.9},
    )
    bad = good.model_copy(update={"player_id": SMOKE_ID_BASE + 999_999})

    await _seed_player(session_factory, SMOKE_ID_BASE + 1, "smoke_pred_a", NOW)

    with pytest.raises(sqla.exc.IntegrityError):
        async with session_factory() as session, session.begin():
            await PredictionRepo().insert(
                async_session=session, predictions=[good, bad]
            )
            await PredictionLatestRepo().insert(
                async_session=session, predictions=[good]
            )

    async with session_factory() as session:
        count = await session.scalar(
            sqla.text(
                f"SELECT COUNT(*) FROM prediction WHERE player_id = {SMOKE_ID_BASE + 1}"
            )
        )
    assert count == 0, "first insert leaked: repo committed inside the batch"

    async with session_factory() as session, session.begin():
        await PredictionRepo().insert(async_session=session, predictions=[good])
        await PredictionLatestRepo().insert(async_session=session, predictions=[good])
    async with session_factory() as session:
        count = await session.scalar(
            sqla.text(
                f"SELECT COUNT(*) FROM prediction WHERE player_id = {SMOKE_ID_BASE + 1}"
            )
        )
    assert count == 1


@pytest.mark.asyncio
async def test_player_update_many_handles_20k_rows_beyond_memory_ceiling(
    session_factory: async_sessionmaker[AsyncSession],
):
    # >16MB of fixed-width rows would kill an ENGINE=MEMORY temp table;
    # id range kept clear of the small fixtures below
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
    async with session_factory() as session, session.begin():
        await session.execute(
            sqla.text(
                """
                INSERT IGNORE INTO Players
                    (id, name, created_at, updated_at, possible_ban,
                     confirmed_ban, confirmed_player, label_id, label_jagex)
                VALUES (:id, :name, :created_at, :updated_at, 0, 0, 1, 0, 0)
                """
            ),
            rows,
        )

    players = [
        PlayerStruct(
            id=row["id"],
            name=row["name"],
            created_at=NOW,
            updated_at=NOW,
        )
        for row in rows
    ]
    async with session_factory() as session, session.begin():
        await PlayerRepo().update_many_players(
            async_session=session, players_data=players
        )

    async with session_factory() as session:
        updated = await session.scalar(
            sqla.text(
                "SELECT COUNT(*) FROM Players "
                f"WHERE id >= {first_id} AND updated_at IS NOT NULL"
            )
        )
    assert updated == total


@pytest.mark.asyncio
async def test_highscore_insert_many_upserts_across_all_partitions(
    session_factory: async_sessionmaker[AsyncSession],
):
    scrape_date = NOW.date()
    batch = [
        HighscoreBaseStruct(
            player_id=SMOKE_ID_BASE + 500 + i,
            scrape_date=scrape_date,
            time_to_live=scrape_date,
            skills={"attack": i},
            activities={},
        )
        for i in range(500)
    ]
    repo = HighscoreDataRepo()
    for _ in range(2):
        async with session_factory() as session, session.begin():
            await repo.insert_highscore_many(
                async_session=session, highscore_data=batch
            )

    async with session_factory() as session:
        for table in (
            "highscore_data_latest",
            "highscore_data_daily",
            "highscore_data_weekly",
            "highscore_data_monthly",
        ):
            count = await session.scalar(
                sqla.text(
                    f"SELECT COUNT(*) FROM {table} "
                    f"WHERE player_id >= {SMOKE_ID_BASE + 500}"
                )
            )
            assert count == 500, f"{table}: duplicate/upsert drifted row count"


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


@pytest.mark.asyncio
async def test_report_insert_dedupes_sightings(
    session_factory: async_sessionmaker[AsyncSession],
):
    repo = ReportRepo()
    detections = [_smoke_detection(1_700_000_000_000 + i * 1000) for i in range(2)]
    for _ in range(2):
        async with session_factory() as session, session.begin():
            await repo.insert(async_session=session, reports=detections)

    async with session_factory() as session:
        count = await session.scalar(
            sqla.text(
                "SELECT COUNT(*) FROM report_sighting "
                f"WHERE reporting_id = {SMOKE_ID_BASE + 900} "
                f"AND reported_id = {SMOKE_ID_BASE + 901}"
            )
        )
    assert count == 1


@pytest.mark.asyncio
async def test_get_report_score_empty_tuple_returns_empty(
    session_factory: async_sessionmaker[AsyncSession],
):
    await _seed_player(session_factory, SMOKE_ID_BASE + 900, "smoke_voter_1", NOW)
    await _seed_player(session_factory, SMOKE_ID_BASE + 901, "smoke_subject_1", NOW)
    async with session_factory() as session, session.begin():
        await ReportRepo().insert(
            async_session=session, reports=[_smoke_detection(1_700_000_000_000)]
        )
    async with session_factory() as session:
        repo = PublicPlayerRepo(session)

        empty = await repo.get_report_score(())
        assert empty == []

        rows = await repo.get_report_score(("smoke_voter_1", "smoke_voter_2"))
        assert len(rows) >= 1


@pytest.mark.asyncio
async def test_set_primary_rsn_miss_does_not_wipe_existing_primary(
    session_factory: async_sessionmaker[AsyncSession],
):
    engine = create_async_engine(SMOKE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: DiscordVerificationTableStruct.__table__.create(
                sync_conn, checkfirst=True
            )
        )
    await engine.dispose()

    async with session_factory() as session, session.begin():
        await session.execute(
            sqla.text(
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
    async with session_factory() as session:
        missed = await repo.set_primary_rsn(
            async_session=session,
            discord_id="smoke_d1",
            player_id=SMOKE_ID_BASE + 999_999,
            is_primary=True,
        )
    assert missed is False

    async with session_factory() as session:
        primaries = await session.scalars(
            sqla.text(
                "SELECT Player_id FROM DiscordVerification "
                "WHERE Discord_id = 'smoke_d1' AND primary_rsn = 1"
            )
        )
    assert list(primaries) == [SMOKE_ID_BASE + 1]

    async with session_factory() as session:
        flipped = await repo.set_primary_rsn(
            async_session=session,
            discord_id="smoke_d1",
            player_id=SMOKE_ID_BASE + 2,
            is_primary=True,
        )
    assert flipped is True
    async with session_factory() as session:
        primaries = await session.scalars(
            sqla.text(
                "SELECT Player_id FROM DiscordVerification "
                "WHERE Discord_id = 'smoke_d1' AND primary_rsn = 1"
            )
        )
    assert list(primaries) == [SMOKE_ID_BASE + 2]


@pytest.mark.asyncio
async def test_session_factory_connects_and_pings():
    settings = Settings(DATABASE_URL=SMOKE_URL)
    factory, engine = get_session_factory(SETTINGS=settings)
    async with factory() as session:
        one = await session.scalar(sqla.text("SELECT 1"))
    await engine.dispose()
    assert one == 1
