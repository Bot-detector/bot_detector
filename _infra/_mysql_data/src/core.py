import asyncio
import json
import random
import sys

import sqlalchemy
from database.database import Session

sys.path.insert(0, "/app/_shared")

from config import MySQLSeederConfig, load_names
from seeders.players import seed_players
from seeders.predictions import create_predictions
from seeders.reports import seed_reports

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
        await seed_players(names=names, count=config.SEED_PLAYERS)

    player_ids = await get_player_ids()

    if config.SEED_PREDICTIONS > 0:
        pred_count = min(config.SEED_PREDICTIONS, len(player_ids))
        for prediction in create_predictions(player_ids=player_ids, count=pred_count):
            sql = sqlalchemy.text("""
            INSERT INTO prediction_latest (player_id, model_name, prediction, confidence, predictions)
            VALUES (:player_id, :model_name, :prediction, :confidence, :predictions)
            ON DUPLICATE KEY UPDATE
                model_name = VALUES(model_name),
                prediction = VALUES(prediction),
                confidence = VALUES(confidence),
                predictions = VALUES(predictions)
            """)
            data = prediction.model_dump(mode="json")
            data["predictions"] = json.dumps(data.get("predictions"))
            print(
                f"  -> Prediction for player {prediction.player_id}: {prediction.prediction}"
            )
            async with Session.begin() as session:
                await session.execute(sql, data)

    if config.SEED_REPORTS > 0:
        await seed_reports(player_ids=player_ids, count=config.SEED_REPORTS)


if __name__ == "__main__":
    asyncio.run(main())
