import json
from asyncio import Queue

import sqlalchemy
from aiokafka import ConsumerRecord
from bot_detector.database.repositories import HighscoreDataDailyRepo, PlayerRepo
from bot_detector.database.structs import HighscoreDataDailyStruct, PlayerStruct
from bot_detector.structs import HighscoreData, Player, ScraperData
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def batch_insert(
    hs_data: list[HighscoreData],
    player_data: list[Player],
    async_session: async_sessionmaker[AsyncSession],
):
    # Step 1: Validate & transform the data
    data_to_insert = [
        HighscoreDataDailyStruct(
            player_id=d.player_id,
            scrape_date=d.scrape_ts.date(),
            skills=d.skills,
            activities=d.activities,
            # scrape_year=d.scrape_ts.year,
            # scrape_month=d.scrape_ts.month,
            # scrape_week=d.scrape_ts.isocalendar().week,
        )
        for d in hs_data
    ]
    data_to_update = [PlayerStruct(**d.model_dump()) for d in player_data]

    # Step 3: Execute the insert statement
    player_repo = PlayerRepo()
    hs_repo = HighscoreDataDailyRepo()

    async with async_session() as session:
        async with session.begin():
            for d in data_to_insert:
                await hs_repo.insert_highscore(async_session=session, highscore_data=d)

            for d in data_to_update:
                await player_repo.update_player(async_session=session, player_data=d)
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
