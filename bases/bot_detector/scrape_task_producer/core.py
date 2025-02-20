import asyncio
import logging
from asyncio import Queue

import sqlalchemy as sqla
from bot_detector.database import Settings as DBSettings
from bot_detector.database import get_session_factory
from bot_detector.database.models import dbPlayer
from bot_detector.kafka_client import KafkaProducer
from bot_detector.schema import Player
from pydantic_settings import BaseSettings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9094"


def create_producer(bootstrap_servers: str) -> KafkaProducer:
    return KafkaProducer(bootstrap_servers=bootstrap_servers)


async def put_players_in_queue(
    players: list[Player],
    queue: Queue,
):
    logger.info(f"Putting {len(players)} players in queue")
    for player in players:
        if not isinstance(player, Player):
            logger.error(f"Invalid player: {player}")
            continue
        await queue.put(player.model_dump(mode="json"))


async def fetch_players(
    async_session: async_sessionmaker[AsyncSession],
    days: int = 7,
    confirmed_ban: bool | None = None,
    player_id: int | None = None,
    limit: int = 10_000,
) -> list[Player]:
    logger.info(
        f"Fetching players with days={days}, confirmed_ban={confirmed_ban}, player_id={player_id}, limit={limit}"
    )
    sql = sqla.select(dbPlayer)

    if days:
        sql = sql.where(
            dbPlayer.updated_at > sqla.func.now() - sqla.text("interval :days day")
        )

    if player_id:
        sql = sql.where(dbPlayer.id > player_id)

    if confirmed_ban is not None:
        sql = sql.where(dbPlayer.confirmed_ban == confirmed_ban)

    if limit:
        sql = sql.limit(limit)

    async with async_session() as session:
        result = await session.execute(sql, params={"days": days})
        # we need mapping to get the column names
        players = result.mappings().all()

    return [Player(**player) for player in players]


async def determine_fetch_params(
    days: int,
    confirmed_ban: bool,
    player_id: int,
    limit: int,
    players: list[Player] | None,
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
    limit = 10_000

    while True:
        players = await fetch_players(
            async_session=async_session,
            days=days,
            confirmed_ban=confirmed_ban,
            player_id=player_id,
            limit=limit,
        )

        await put_players_in_queue(queue=queue, players=players)

        days, confirmed_ban, player_id, limit = await determine_fetch_params(
            days=days,
            confirmed_ban=confirmed_ban,
            player_id=player_id,
            limit=limit,
            players=players,
            max_days=7,
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
