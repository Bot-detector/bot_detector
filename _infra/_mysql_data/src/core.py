import asyncio
import json
import random
import sys

import sqlalchemy
from database.database import Session

sys.path.insert(0, "/app/_shared")

from config import MySQLSeederConfig, load_names
from seeders.players import Player, create_players
from seeders.predictions import PredictionLatest, create_predictions
from seeders.reports import (
    Report,
    ReportGear,
    ReportLocation,
    ReportSighting,
    create_report_gear,
    create_report_locations,
    create_report_sightings,
    create_reports,
)

config = MySQLSeederConfig()


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
    VALUES (:player_id, :model_name, :prediction, :confidence, :predictions)
    ON DUPLICATE KEY UPDATE
        model_name = VALUES(model_name),
        prediction = VALUES(prediction),
        confidence = VALUES(confidence),
        predictions = VALUES(predictions)
    """)

    pred_count = min(count, len(player_ids))
    for prediction in create_predictions(player_ids=player_ids, count=pred_count):
        data = prediction.model_dump(mode="json")
        data["predictions"] = json.dumps(data.get("predictions"))
        print(f"  -> Prediction for player {prediction.player_id}: {prediction.prediction}")
        async with Session.begin() as session:
            await session.execute(sql, data)


async def insert_reports(player_ids: list[int], count: int) -> None:
    sighting_ids: list[int] = []
    gear_ids: list[int] = []
    location_ids: list[int] = []

    sighting_sql = sqlalchemy.text("""
    INSERT IGNORE INTO report_sighting (reporting_id, reported_id, manual_detect)
    VALUES (:reporting_id, :reported_id, :manual_detect)
    """)
    gear_sql = sqlalchemy.text("""
    INSERT IGNORE INTO report_gear (
        equip_head_id, equip_amulet_id, equip_torso_id, equip_legs_id,
        equip_boots_id, equip_cape_id, equip_hands_id, equip_weapon_id, equip_shield_id
    ) VALUES (
        :equip_head_id, :equip_amulet_id, :equip_torso_id, :equip_legs_id,
        :equip_boots_id, :equip_cape_id, :equip_hands_id, :equip_weapon_id, :equip_shield_id
    )
    """)
    location_sql = sqlalchemy.text("""
    INSERT IGNORE INTO report_location (region_id, x_coord, y_coord, z_coord)
    VALUES (:region_id, :x_coord, :y_coord, :z_coord)
    """)
    report_sql = sqlalchemy.text("""
    INSERT INTO report (report_sighting_id, report_location_id, report_gear_id,
        reported_at, on_members_world, on_pvp_world, world_number, region_id)
    VALUES (:report_sighting_id, :report_location_id, :report_gear_id,
        :reported_at, :on_members_world, :on_pvp_world, :world_number, :region_id)
    """)

    for sighting in create_report_sightings(player_ids=player_ids, count=count):
        async with Session.begin() as session:
            result = await session.execute(sighting_sql, sighting.model_dump(mode="json"))
            sighting_ids.append(result.lastrowid)

    for gear in create_report_gear(count=count):
        async with Session.begin() as session:
            result = await session.execute(gear_sql, gear.model_dump(mode="json"))
            gear_ids.append(result.lastrowid)

    for location in create_report_locations(count=count):
        async with Session.begin() as session:
            result = await session.execute(location_sql, location.model_dump(mode="json"))
            location_ids.append(result.lastrowid)

    for report in create_reports(
        sighting_ids=sighting_ids,
        gear_ids=gear_ids,
        location_ids=location_ids,
        count=count,
    ):
        async with Session.begin() as session:
            await session.execute(report_sql, report.model_dump(mode="json"))

    print(f"Seeded {count} reports")


async def main():
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


if __name__ == "__main__":
    asyncio.run(main())
