import asyncio
import logging
from datetime import date, datetime, time

from bot_detector.database import Settings as DBSettings
from bot_detector.database import get_session_factory
from bot_detector.database.interfaces import playerInterface
from bot_detector.database.repositories import PlayerRepo
from bot_detector.kafka import Settings as KafkaSettings
from bot_detector.kafka.interface import ConsumerInterface, ProducerInterface
from bot_detector.kafka.repositories import (
    RepoPlayersToScrapeConsumer,
    RepoPlayersToScrapeProducer,
)
from bot_detector.structs import MetaData, PlayerStruct, ToScrapeStruct
from pydantic_settings import BaseSettings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    LIMIT: int = 10_000


async def produce_players(
    players: list[PlayerStruct],
    player_producer: RepoPlayersToScrapeProducer,
):
    logger.info(f"Putting {len(players)} players in queue")
    player_structs = [
        ToScrapeStruct(
            metadata=MetaData(version=1, source="scrape_task_producer"),
            player_data=player,
        )
        for player in players
        if len(player.name) <= 13
    ]

    for player in player_structs:
        await player_producer.produce_one(player=player)


def determine_fetch_params(
    days: int,
    confirmed_ban: bool,
    player_id: int,
    limit: int,
    players: list[PlayerStruct] | None,
    max_days: int = 7,
):
    if players is None:
        return days, confirmed_ban, player_id

    if len(players) < limit and days > 1:
        logger.info("No more players to scrape, reducing days")
        return days - 1, confirmed_ban, 0

    if len(players) < limit and days == 1 and not confirmed_ban:
        logger.info("No more players to scrape, looking for confirmed bans")
        return max_days, True, 0

    if len(players) < limit and days == 5 and confirmed_ban:
        logger.info("No more players to scrape, resetting")
        return max_days, False, 0

    return days, confirmed_ban, players[-1].id


async def process_players(
    async_session: async_sessionmaker[AsyncSession],
    player_repo: playerInterface,
    player_producer: ProducerInterface,
    player_consumer: ConsumerInterface,
    limit: int = 10,
):
    player_id = 0
    days = 7
    confirmed_ban = False
    max_days = 7
    last_day = date.today()

    while True:
        lag = await player_consumer.get_lag()

        if last_day != date.today():
            logger.info("New day detected, resetting days and confirmed_ban")
            last_day = date.today()
            days = max_days
            confirmed_ban = False
            player_id = 0

        if lag >= 100_000:
            logger.info(f"{lag=} to high, sleeping(10)")
            await asyncio.sleep(10)
            continue

        logger.info(f"{player_id=}, {confirmed_ban=}, {days=}, {limit=}")

        async with async_session() as session:
            players = await player_repo.select_player(
                async_session=session,
                player_id=player_id,
                confirmed_ban=confirmed_ban,
                days=days,
                limit=limit,
            )

        await produce_players(players=players, player_producer=player_producer)

        days, confirmed_ban, player_id = determine_fetch_params(
            players=players,
            player_id=player_id,
            confirmed_ban=confirmed_ban,
            days=days,
            max_days=max_days,
            limit=limit,
        )

        # sleep the remaining time of the current day
        if (days, confirmed_ban, player_id) == (max_days, False, 0):
            now = datetime.now()
            end_of_today = datetime.combine(now.date(), time.max)

            time_remaining = end_of_today - now
            sleep_time = int(time_remaining.total_seconds() / 4)
            sleep_time = max(sleep_time, 1)  # Ensure at least 1 second sleep
            logger.info(f"Sleeping for {sleep_time} seconds until end of day (1/4)")
            await asyncio.sleep(sleep_time)


async def main():
    async_session, async_engine = get_session_factory(SETTINGS=DBSettings())

    bootstrap_servers = KafkaSettings().KAFKA_BOOTSTRAP_SERVERS
    player_producer = RepoPlayersToScrapeProducer(bootstrap_servers=bootstrap_servers)
    player_consumer = RepoPlayersToScrapeConsumer(
        bootstrap_servers=bootstrap_servers, group_id="scraper"
    )

    await player_producer.start()
    await player_consumer.start()

    try:
        await process_players(
            async_session=async_session,
            player_repo=PlayerRepo(),
            player_producer=player_producer,
            player_consumer=player_consumer,
            limit=Settings().LIMIT,
        )
    finally:
        await async_engine.dispose()
        await player_producer.stop()
        await player_consumer.stop()


async def run_async():
    await main()


def run():
    asyncio.run(run_async())


if __name__ == "__main__":
    run()
