import asyncio
import logging
from asyncio import Queue
from dataclasses import asdict

from bot_detector.database import Settings as DBSettings
from bot_detector.database import get_session_factory
from bot_detector.database.repositories import PlayerRepo
from bot_detector.database.structs import PlayerStruct
from bot_detector.kafka_client import KafkaProducer
from pydantic_settings import BaseSettings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9094"


def create_producer(bootstrap_servers: str) -> KafkaProducer:
    return KafkaProducer(bootstrap_servers=bootstrap_servers)


async def put_players_in_queue(
    players: list[PlayerStruct],
    queue: Queue,
):
    logger.info(f"Putting {len(players)} players in queue")
    for player in players:
        if not isinstance(player, PlayerStruct):
            logger.error(f"Invalid player: {player}")
            continue
        await queue.put(asdict(player))


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

    if len(players) < limit and days == 1 and not confirmed_ban:
        logger.info("No more players to scrape, looking for confirmed bans")
        return max_days, True, 0, limit

    if len(players) < limit and days == 1 and confirmed_ban:
        logger.info("No more players to scrape, resetting")
        await asyncio.sleep(60)
        return max_days, False, 0, limit

    return days, confirmed_ban, players[-1].id, limit


async def work(async_session: async_sessionmaker[AsyncSession], queue: Queue):
    player_id = 0
    days = 7
    confirmed_ban = False
    limit = 10

    player_repo = PlayerRepo()
    while True:
        async with async_session() as session:
            players = await player_repo.select_player(
                async_session=session,
                player_id=player_id,
                confirmed_ban=confirmed_ban,
                days=days,
                limit=limit,
            )

        await put_players_in_queue(queue=queue, players=players)

        days, confirmed_ban, player_id, limit = await determine_fetch_params(
            players=players,
            player_id=player_id,
            confirmed_ban=confirmed_ban,
            days=days,
            max_days=7,
            limit=limit,
        )


async def main():
    async_session, async_engine = get_session_factory(SETTINGS=DBSettings())
    producer = create_producer(bootstrap_servers=Settings().KAFKA_BOOTSTRAP_SERVERS)
    to_scrape_queue = Queue()

    tasks = [
        producer.produce(
            topic="players.to_scrape",
            queue=to_scrape_queue,
        ),
        work(
            async_session=async_session,
            queue=to_scrape_queue,
        ),
    ]
    await asyncio.gather(*tasks)
    await async_engine.dispose()


def run():
    asyncio.run(main())


if __name__ == "__main__":
    run()
