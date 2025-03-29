import asyncio
import logging

from bot_detector.database import Settings as DBSettings
from bot_detector.database import get_session_factory
from bot_detector.database.interfaces import playerInterface
from bot_detector.database.repositories import PlayerRepo
from bot_detector.database.structs import PlayerStruct
from bot_detector.kafka import Settings as KafkaSettings
from bot_detector.kafka.interface import PlayersToScrapeProducerInterface
from bot_detector.kafka.repositories import RepoPlayersToScrapeProducer
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


async def produce_players(
    players: list[PlayerStruct],
    player_producer: RepoPlayersToScrapeProducer,
):
    logger.info(f"Putting {len(players)} players in queue")
    for player in players:
        await player_producer.produce_one(player=player)


async def determine_fetch_params(
    days: int,
    confirmed_ban: bool,
    player_id: int,
    limit: int,
    players: list[PlayerStruct] | None,
    max_days: int = 7,
):
    if players is None:
        return days, confirmed_ban, player_id, limit

    if len(players) < limit and days > 1:
        logger.info("No more players to scrape, reducing days")
        return days - 1, confirmed_ban, 0, limit

    if len(players) < limit and days <= 1 and not confirmed_ban:
        logger.info("No more players to scrape, looking for confirmed bans")
        return max_days, True, 0, limit

    if len(players) < limit and days <= 1 and confirmed_ban:
        logger.info("No more players to scrape, resetting")
        await asyncio.sleep(60)
        return max_days, False, 0, limit

    last_player_id = players[-1].id if players else 0
    return days, confirmed_ban, last_player_id, limit


async def work(
    async_session: async_sessionmaker[AsyncSession],
    player_repo: playerInterface,
    player_producer: PlayersToScrapeProducerInterface,
):
    player_id = 0
    days = 7
    confirmed_ban = False
    limit = 10

    while True:
        logger.info(f"{player_id=}, {confirmed_ban=}, {days=}, {limit=}")
        # print(f"{player_id=}, {confirmed_ban=}, {days=}, {limit=}")
        async with async_session() as session:
            players = await player_repo.select_player(
                async_session=session,
                player_id=player_id,
                confirmed_ban=confirmed_ban,
                days=days,
                limit=limit,
            )

        await produce_players(players=players, player_producer=player_producer)

        days, confirmed_ban, player_id, limit = await determine_fetch_params(
            players=players,
            player_id=player_id,
            confirmed_ban=confirmed_ban,
            days=days,
            max_days=7,
            limit=limit,
        )


async def main(
    async_session: async_sessionmaker,
    async_engine: AsyncEngine,
    player_repo: playerInterface,
    player_producer: PlayersToScrapeProducerInterface,
):
    await player_producer.start()

    try:
        await work(
            async_session=async_session,
            player_repo=player_repo,
            player_producer=player_producer,
        )
    finally:
        await async_engine.dispose()
        await player_producer.stop()


def run():
    async_session, async_engine = get_session_factory(SETTINGS=DBSettings())
    player_repo = PlayerRepo()
    player_producer = RepoPlayersToScrapeProducer(
        bootstrap_servers=KafkaSettings().KAFKA_BOOTSTRAP_SERVERS
    )
    asyncio.run(main(async_session, async_engine, player_repo, player_producer))


if __name__ == "__main__":
    run()
