import asyncio
import json
import random
import sys
from datetime import datetime, timedelta

import sqlalchemy
from database.database import Session, wait_for_db

sys.path.insert(0, "/app/_shared")

from config import MySQLSeederConfig, load_names
from seeders.players import create_players
from seeders.predictions import create_predictions
from seeders.reports import (
    Report,
    create_report_gear,
    create_report_locations,
    create_report_sightings,
    create_reports,
)

config = MySQLSeederConfig()

SIGHTING_SQL = sqlalchemy.text("""
INSERT IGNORE INTO report_sighting (reporting_id, reported_id, manual_detect)
VALUES (:reporting_id, :reported_id, :manual_detect)
""")
SIGHTING_LOOKUP_SQL = sqlalchemy.text("""
SELECT report_sighting_id FROM report_sighting
WHERE reporting_id = :reporting_id
  AND reported_id = :reported_id
  AND manual_detect = :manual_detect
""")
GEAR_SQL = sqlalchemy.text("""
INSERT IGNORE INTO report_gear (
    equip_head_id, equip_amulet_id, equip_torso_id, equip_legs_id,
    equip_boots_id, equip_cape_id, equip_hands_id, equip_weapon_id, equip_shield_id
) VALUES (
    :equip_head_id, :equip_amulet_id, :equip_torso_id, :equip_legs_id,
    :equip_boots_id, :equip_cape_id, :equip_hands_id, :equip_weapon_id, :equip_shield_id
)
""")
GEAR_LOOKUP_SQL = sqlalchemy.text("""
SELECT report_gear_id FROM report_gear
WHERE equip_head_id <=> :equip_head_id
  AND equip_amulet_id <=> :equip_amulet_id
  AND equip_torso_id <=> :equip_torso_id
  AND equip_legs_id <=> :equip_legs_id
  AND equip_boots_id <=> :equip_boots_id
  AND equip_cape_id <=> :equip_cape_id
  AND equip_hands_id <=> :equip_hands_id
  AND equip_weapon_id <=> :equip_weapon_id
  AND equip_shield_id <=> :equip_shield_id
""")
LOCATION_SQL = sqlalchemy.text("""
INSERT IGNORE INTO report_location (region_id, x_coord, y_coord, z_coord)
VALUES (:region_id, :x_coord, :y_coord, :z_coord)
""")
LOCATION_LOOKUP_SQL = sqlalchemy.text("""
SELECT report_location_id FROM report_location
WHERE region_id = :region_id
  AND x_coord = :x_coord
  AND y_coord = :y_coord
  AND z_coord = :z_coord
""")
REPORT_SQL = sqlalchemy.text("""
INSERT IGNORE INTO report (report_sighting_id, report_location_id, report_gear_id,
    reported_at, on_members_world, on_pvp_world, world_number, region_id)
VALUES (:report_sighting_id, :report_location_id, :report_gear_id,
    :reported_at, :on_members_world, :on_pvp_world, :world_number, :region_id)
""")


async def insert_ignore_get_id(
    insert_sql: sqlalchemy.TextClause,
    lookup_sql: sqlalchemy.TextClause,
    params: dict,
) -> int:
    """Insert a row and return its id, resolving duplicates by unique key.

    INSERT IGNORE returns lastrowid 0 when the row was skipped, so the id of
    the existing row is looked up by its unique key instead.
    """
    async with Session.begin() as session:
        result = await session.execute(insert_sql, params)
        row_id = result.lastrowid
        if row_id:
            return row_id
        existing = await session.execute(lookup_sql, params)
        return existing.scalar() or 0


async def get_player_count() -> int:
    sql = sqlalchemy.text("""
    SELECT COUNT(*) FROM Players;
    """)
    async with Session.begin() as session:
        result = await session.execute(sql)
        count = result.scalar() or 0
    print(f"Total players: {count}")
    return count


async def get_player_ids() -> list[int]:
    sql = sqlalchemy.text("""
    SELECT id FROM Players ORDER BY id;
    """)
    async with Session.begin() as session:
        result = await session.execute(sql)
        ids = [row[0] for row in result.fetchall()]
    return ids


async def insert_players(names: list[str], count: int) -> list[int]:
    player_ids = []
    sql = sqlalchemy.text("""
    INSERT IGNORE INTO Players (id, name, created_at)
    VALUES (:id, :name, :created_at)
    """)
    get_id_sql = sqlalchemy.text("SELECT id FROM Players WHERE name = :name")

    for player in create_players(names=names, count=count):
        print(player.name)
        async with Session.begin() as session:
            await session.execute(sql, player.model_dump(mode="json"))
        async with Session.begin() as session:
            result = await session.execute(get_id_sql, {"name": player.name})
            row = result.fetchone()
            if row:
                player_ids.append(row[0])

    print(f"Seeded {len(player_ids)} players")
    return player_ids


async def insert_predictions(player_ids: list[int], count: int) -> None:
    sql = sqlalchemy.text("""
    INSERT INTO prediction_latest (player_id, model_name, prediction, confidence, predictions)
    VALUES (:player_id, :model_name, :prediction, :confidence, :predictions) AS new_val
    ON DUPLICATE KEY UPDATE
        model_name = new_val.model_name,
        prediction = new_val.prediction,
        confidence = new_val.confidence,
        predictions = new_val.predictions
    """)

    pred_count = min(count, len(player_ids))
    for prediction in create_predictions(player_ids=player_ids, count=pred_count):
        data = prediction.model_dump(mode="json")
        data["predictions"] = json.dumps(data.get("predictions"))
        print(
            f"  -> Prediction for player {prediction.player_id}: {prediction.prediction}"
        )
        async with Session.begin() as session:
            await session.execute(sql, data)


async def insert_reports(player_ids: list[int], count: int) -> None:
    sighting_ids: list[int] = []
    gear_ids: list[int] = []
    location_ids: list[int] = []

    for sighting in create_report_sightings(player_ids=player_ids, count=count):
        sighting_ids.append(
            await insert_ignore_get_id(
                SIGHTING_SQL, SIGHTING_LOOKUP_SQL, sighting.model_dump(mode="json")
            )
        )

    for gear in create_report_gear(count=count):
        gear_ids.append(
            await insert_ignore_get_id(
                GEAR_SQL, GEAR_LOOKUP_SQL, gear.model_dump(mode="json")
            )
        )

    for location in create_report_locations(count=count):
        location_ids.append(
            await insert_ignore_get_id(
                LOCATION_SQL, LOCATION_LOOKUP_SQL, location.model_dump(mode="json")
            )
        )

    inserted = 0
    for report in create_reports(
        sighting_ids=sighting_ids,
        gear_ids=gear_ids,
        location_ids=location_ids,
        count=count,
    ):
        async with Session.begin() as session:
            result = await session.execute(REPORT_SQL, report.model_dump(mode="json"))
            inserted += result.rowcount

    print(f"Seeded {inserted} reports ({count - inserted} duplicates skipped)")


async def insert_aged_reports(
    player_ids: list[int], retention_days: int, count: int
) -> None:
    """Seed report rows that straddle the prune retention cutoff.

    Roughly half are inserted with reported_at older than the cutoff (so the
    prune job has rows to delete) and half younger (retained).
    """
    sighting_ids: list[int] = []
    gear_ids: list[int] = []
    location_ids: list[int] = []

    for sighting in create_report_sightings(player_ids=player_ids, count=count):
        sighting_ids.append(
            await insert_ignore_get_id(
                SIGHTING_SQL, SIGHTING_LOOKUP_SQL, sighting.model_dump(mode="json")
            )
        )

    for gear in create_report_gear(count=count):
        gear_ids.append(
            await insert_ignore_get_id(
                GEAR_SQL, GEAR_LOOKUP_SQL, gear.model_dump(mode="json")
            )
        )

    for location in create_report_locations(count=count):
        location_ids.append(
            await insert_ignore_get_id(
                LOCATION_SQL, LOCATION_LOOKUP_SQL, location.model_dump(mode="json")
            )
        )

    cutoff = datetime.now() - timedelta(days=retention_days)
    old_count = count // 2

    inserted = 0
    for i in range(count):
        if i < old_count:
            reported_at = cutoff - timedelta(days=random.randint(1, 30))
        else:
            reported_at = cutoff + timedelta(days=random.randint(1, 30))

        sighting_id = (
            sighting_ids[i] if i < len(sighting_ids) else random.choice(sighting_ids)
        )
        gear_id = gear_ids[i] if i < len(gear_ids) else random.choice(gear_ids)
        location_id = (
            location_ids[i] if i < len(location_ids) else random.choice(location_ids)
        )

        report = Report(
            report_sighting_id=sighting_id,
            report_location_id=location_id,
            report_gear_id=gear_id,
            reported_at=reported_at,
            on_members_world=random.choice([0, 1]),
            on_pvp_world=random.choice([0, 0, 0, 1]),
            world_number=random.randint(300, 500),
            region_id=random.randint(1, 15000),
        )
        async with Session.begin() as session:
            result = await session.execute(REPORT_SQL, report.model_dump(mode="json"))
            inserted += result.rowcount

    print(
        f"Seeded {inserted} aged reports "
        f"({count - inserted} duplicates skipped, "
        f"{old_count} older than {retention_days}d retention cutoff)"
    )


async def mark_banned_players(player_ids: list[int], count: int) -> None:
    sql = sqlalchemy.text("""
    UPDATE Players SET label_jagex = 2, confirmed_ban = 1
    WHERE id = :id
    """)
    banned_ids = random.sample(player_ids, min(count, len(player_ids)))
    for pid in banned_ids:
        async with Session.begin() as session:
            await session.execute(sql, {"id": pid})
    print(f"Marked {len(banned_ids)} players as banned (label_jagex=2)")


async def main():
    await wait_for_db()
    random.seed(config.RANDOM_SEED)

    names = load_names(config.NAMES_FILE)

    if config.SKIP_IF_EXISTING:
        player_count = await get_player_count()
        if player_count > config.SKIP_THRESHOLD:
            print(
                f"Players ({player_count}) > threshold ({config.SKIP_THRESHOLD}), skipping insertion."
            )
            return

    if config.SEED_PLAYERS > 0:
        player_ids = await insert_players(names=names, count=config.SEED_PLAYERS)
    else:
        player_ids = await get_player_ids()

    if config.SEED_PREDICTIONS > 0:
        await insert_predictions(player_ids=player_ids, count=config.SEED_PREDICTIONS)

    if config.SEED_REPORTS > 0:
        await insert_reports(player_ids=player_ids, count=config.SEED_REPORTS)

    if config.SEED_AGED_REPORTS > 0:
        await insert_aged_reports(
            player_ids=player_ids,
            retention_days=config.SEED_RETENTION_DAYS,
            count=config.SEED_AGED_REPORTS,
        )

    if config.SEED_BANNED > 0:
        await mark_banned_players(player_ids=player_ids, count=config.SEED_BANNED)


if __name__ == "__main__":
    asyncio.run(main())
