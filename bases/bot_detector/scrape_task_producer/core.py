import asyncio
import logging
from dataclasses import asdict, dataclass
from datetime import date, datetime, time

from bot_detector.database import Settings as DBSettings
from bot_detector.database import get_session_factory
from bot_detector.database.repositories import PlayerRepo
from bot_detector.kafka import Settings as KafkaSettings
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


@dataclass
class FetchParams:
    days: int = 7
    confirmed_ban: bool = False
    possible_ban: bool = False
    player_id: int = 0
    limit: int = 10_000


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
    fetch_params: FetchParams,
    players: list[PlayerStruct] | None,
    max_days: int = 7,
    max_possible_ban_days: int = 2,
    max_confirmed_ban_days: int = 7,
) -> FetchParams:
    def _reduce_days(fetch_params: FetchParams) -> FetchParams:
        logger.info(f"Reducing days for {asdict(fetch_params)}")
        fetch_params.days = fetch_params.days - 1 if fetch_params.days > 1 else 1
        fetch_params.player_id = 0
        return fetch_params

    if players is None:
        return fetch_params

    if not fetch_params.possible_ban and fetch_params.confirmed_ban:
        logger.warning(
            "Confirmed ban is True but possible_ban is False, resetting confirmed_ban"
        )
        fetch_params.possible_ban = True

    if len(players) < fetch_params.limit:
        # reduce days
        if fetch_params.days > 1:
            if not fetch_params.confirmed_ban and not fetch_params.possible_ban:
                logger.info("No players found, reducing days")
                return _reduce_days(fetch_params)
            elif (
                fetch_params.possible_ban
                and not fetch_params.confirmed_ban
                and fetch_params.days > max_possible_ban_days
            ):
                return _reduce_days(fetch_params)
            elif (
                fetch_params.possible_ban
                and fetch_params.confirmed_ban
                and fetch_params.days > max_confirmed_ban_days
            ):
                return _reduce_days(fetch_params)

        # change state
        if (
            fetch_params.days <= 1
            and not fetch_params.possible_ban
            and not fetch_params.confirmed_ban
        ):
            logger.info("No players found, setting possible_ban to True")
            fetch_params.days = max_days
            fetch_params.possible_ban = True
            fetch_params.player_id = 0
            return fetch_params

        if (
            fetch_params.days <= max_possible_ban_days
            and fetch_params.possible_ban
            and not fetch_params.confirmed_ban
        ):
            logger.info("all Possible ban scraped, setting confirmed_ban to True")
            fetch_params.days = max_days
            fetch_params.confirmed_ban = True
            fetch_params.player_id = 0
            return fetch_params

        if (
            fetch_params.days <= max_confirmed_ban_days
            and fetch_params.possible_ban
            and fetch_params.confirmed_ban
        ):
            logger.info("all Confirmed ban scraped, resetting to default")
            fetch_params.days = max_days
            fetch_params.confirmed_ban = False
            fetch_params.possible_ban = False
            fetch_params.player_id = 0
            return fetch_params

    fetch_params.player_id = players[-1].id
    return fetch_params


async def process_players(
    async_session: async_sessionmaker[AsyncSession],
    player_repo: PlayerRepo,
    player_producer: RepoPlayersToScrapeProducer,
    player_consumer: RepoPlayersToScrapeConsumer,
    limit: int = 10,
):
    fp = FetchParams(
        days=7,
        confirmed_ban=False,
        possible_ban=False,
        player_id=0,
        limit=limit,
    )

    max_days = 7
    last_day = date.today()

    while True:
        lag = await player_consumer.get_lag()

        if last_day != date.today():
            logger.info("New day detected, resetting days and confirmed_ban")
            last_day = date.today()
            fp.days = max_days
            fp.confirmed_ban = False
            fp.possible_ban = False
            fp.player_id = 0

        if lag >= 100_000:
            logger.info(f"{lag=} to high, sleeping(10)")
            await asyncio.sleep(10)
            continue

        logger.info(f"{fp.player_id=}, {fp.confirmed_ban=}, {fp.days=}, {fp.limit=}")

        async with async_session() as session:
            players = await player_repo.select_player(
                async_session=session,
                player_id=fp.player_id,
                possible_ban=fp.possible_ban,
                confirmed_ban=fp.confirmed_ban,
                days=fp.days,
                limit=limit,
            )

        await produce_players(players=players, player_producer=player_producer)

        fp = determine_fetch_params(
            fetch_params=fp,
            players=players,
            max_days=max_days,
        )

        if all(
            [
                fp.days == max_days,
                not fp.possible_ban,
                not fp.confirmed_ban,
                fp.player_id == 0,
            ]
        ):
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
