import json
from asyncio import Queue

import sqlalchemy
from aiokafka import ConsumerRecord
from bot_detector.schema import HighscoreData, Player, ScraperData
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def batch_insert(
    hs_data: list[HighscoreData],
    player_data: list[Player],
    async_session: async_sessionmaker[AsyncSession],
):
    # Step 1: Construct the statements
    ## insert into highscore_data
    sql_insert_hs = sqlalchemy.text("""
        INSERT INTO highscore_data (player_id, scrape_ts, skills, activities) 
        VALUES (:player_id, :scrape_ts, :skills, :activities) AS new
        ON DUPLICATE KEY UPDATE
            scrape_ts = CASE
                WHEN highscore_data.scrape_ts < new.scrape_ts THEN new.scrape_ts
                ELSE highscore_data.scrape_ts
            END,
            skills = CASE
                WHEN highscore_data.scrape_ts < new.scrape_ts THEN new.skills
                ELSE highscore_data.skills
            END,
            activities = CASE
                WHEN highscore_data.scrape_ts < new.scrape_ts THEN new.activities
                ELSE highscore_data.activities
            END
    """)

    sql_update_player = sqlalchemy.text("""
        UPDATE Players 
        SET 
            updated_at = :updated_at,
            possible_ban = :possible_ban,
            confirmed_ban = :confirmed_ban,
            confirmed_player = :confirmed_player,
            label_id = :label_id,
            label_jagex = :label_jagex
        WHERE 1=1
            AND id = :id 
            AND (updated_at < :updated_at OR updated_at IS NULL)
    """)

    # Step2: Transform the data into dictionaries for parameterized insertion
    data_to_insert = [
        {
            "player_id": d.player_id,
            "scrape_ts": d.scrape_ts,
            "skills": json.dumps(d.skills),  # Serialize skills as JSON
            "activities": json.dumps(d.activities),  # Serialize activities as JSON
        }
        for d in hs_data
    ]
    data_to_update = [
        {
            "id": d.id,
            "updated_at": d.updated_at,
            "possible_ban": d.possible_ban,
            "confirmed_ban": d.confirmed_ban,
            "confirmed_player": d.confirmed_player,
            "label_id": d.label_id,
            "label_jagex": d.label_jagex,
        }
        for d in player_data
    ]

    # Step 3: Execute the insert statement
    async with async_session() as session:
        async with session.begin():
            if data_to_insert:
                await session.execute(sql_insert_hs, data_to_insert)
            for d in data_to_update:
                await session.execute(sql_update_player, d)
            await session.commit()


def extract_data_from_batch(
    batch: list[ScraperData],
) -> tuple[list[Player], list[HighscoreData]]:
    players: dict[int, Player] = {}
    hiscores: dict[int, dict[str, HighscoreData]] = {}

    for msg in batch:
        new_player = msg.player_data

        # Update player data if necessary
        if new_player.id not in players:
            players[new_player.id] = new_player
        elif players[new_player.id].updated_at < new_player.updated_at:
            players[new_player.id] = new_player

        if msg.hiscore_data is None:
            continue

        new_hs = HighscoreData(
            player_id=new_player.id,
            scrape_ts=new_player.updated_at,
            skills=msg.hiscore_data.skills,
            activities=msg.hiscore_data.activities,
        )
        new_year = new_hs.scrape_ts.isocalendar().year
        new_week = new_hs.scrape_ts.isocalendar().week
        key = f"{new_year}:{new_week}"

        if new_player.id not in hiscores:
            hiscores[new_player.id] = {key: new_hs}
        else:
            # Retrieve the current hiscore and compare
            existing_key = list(hiscores[new_player.id].keys())[0]
            existing_hs = hiscores[new_player.id][existing_key]
            old_year, old_week = map(int, existing_key.split(":"))

            if new_year > int(old_year):
                hiscores[new_player.id] = {key: new_hs}
            elif new_year == int(old_year) and new_week > int(old_week):
                hiscores[new_player.id] = {key: new_hs}
            elif (
                new_year == int(old_year)
                and new_week == int(old_week)
                and new_hs.scrape_ts > existing_hs.scrape_ts
            ):
                hiscores[new_player.id] = {key: new_hs}

    # Flatten hiscores and players to lists
    return (
        list(players.values()),
        [hs for hs_dict in hiscores.values() for hs in hs_dict.values()],
    )


async def process_data(
    queue: Queue,
    error_queue: Queue,
    async_session: async_sessionmaker[AsyncSession],
):
    while True:
        batch: list[ConsumerRecord] = await queue.get()

        # Use the pure function to extract data
        (players, hiscores) = extract_data_from_batch(
            [ScraperData(**m.value) for m in batch]
        )

        await batch_insert(
            hs_data=hiscores,
            player_data=players,
            async_session=async_session,
        )
