import asyncio
import logging
from datetime import date, datetime
from typing import Any

from aiohttp import ClientSession
from bot_detector.kafka import Settings as KafkaSettings
from bot_detector.kafka.repositories import (
    RepoPlayerScrapedProducer,
    RepoPlayersNotFoundProducer,
    RepoPlayersToScrapeConsumer,
    RepoPlayersToScrapeProducer,
)
from bot_detector.proxy_manager import ProxyManager
from bot_detector.proxy_manager import Settings as ProxySettings
from bot_detector.structs import (
    HighscoreBaseStruct,
    MetaData,
    PlayerStruct,
)
from bot_detector.structs.kafka import NotFoundStruct, ScrapedStruct
from osrs.asyncio import Hiscore, HSMode
from osrs.asyncio.osrs.hiscores import PlayerStats
from osrs.exceptions import PlayerDoesNotExist, UnexpectedRedirection
from osrs.utils import RateLimiter
from pydantic import ValidationError

logger = logging.getLogger(__name__)


async def get_proxy(
    proxy_manager: ProxyManager,
    worker_id: int,
) -> str:
    proxy, error = await proxy_manager.get_proxy(worker_id)
    if error:
        logger.error(f"Worker {worker_id}: {error}")
        return None
    return proxy


async def scrape_player(
    player: PlayerStruct,
    proxy: str,
    session: ClientSession,
) -> tuple[PlayerStats | None, str | None]:
    player_stats, error = None, None

    hiscore_instance = Hiscore(
        proxy=proxy,
        rate_limiter=RateLimiter(calls_per_interval=100, interval=60),
    )

    try:
        player_stats = await hiscore_instance.get(
            mode=HSMode.OLDSCHOOL,
            player=player.name,
            session=session,
        )
        return player_stats, error
    except PlayerDoesNotExist:
        logger.error(f"Player: {player.name} does not exist.")
        return None, error
    except UnexpectedRedirection:
        error = f"Unexpected redirection for player {player.name}."
        logger.error(error)
        return None, error


async def transform_player_stats(
    player_stats: PlayerStats,
    player: PlayerStruct,
) -> tuple[ScrapedStruct | None, Any | None]:
    player.updated_at = datetime.now()

    skills = {s.name: s.xp for s in player_stats.skills if s.xp > 0}
    activities = {a.name: a.score for a in player_stats.activities if a.score > 0}

    hiscore_data, error = None, None
    try:
        hiscore_data = ScrapedStruct(
            metadata=MetaData(version=1, source="hiscore_scraper"),
            player_data=player,
            highscore_data=HighscoreBaseStruct(
                player_id=player.id,
                scrape_date=date.today(),
                skills=skills,
                activities=activities,
            ),
        )
    except ValidationError as e:
        error = e.json()
        logger.error(error)
        return None, error
    return hiscore_data, error


async def work(
    worker_id: int,
    proxy_manager: ProxyManager,
    player_ts_consumer: RepoPlayersToScrapeConsumer,
    player_ts_producer: RepoPlayersToScrapeProducer,
    player_nf_producer: RepoPlayersNotFoundProducer,
    player_sc_producer: RepoPlayerScrapedProducer,
):
    async with ClientSession() as session:
        while True:
            # get proxy
            proxy = await get_proxy(proxy_manager, worker_id)

            # handle exceptions
            if proxy is None:
                logger.error(f"[{worker_id}]: No proxy available.")
                await asyncio.sleep(10)
                continue

            # get player from kafka
            try:
                player = await player_ts_consumer.consume_one()
            except ValidationError as e:
                logger.error(e.json())
                continue

            player_data = player.player_data

            # handle exceptions
            if player is None:
                logger.error(f"[{worker_id}]: No player available.")
                await asyncio.sleep(10)
                continue

            player_stats, error = await scrape_player(
                player=player_data, proxy=proxy, session=session
            )

            # handle exceptions
            if error:
                logger.error(f"[{worker_id}]: Error scraping {player_data.name}.")
                await player_ts_producer.produce_one(player=player)
                await asyncio.sleep(10)
                continue

            # if player not found, than send to not found topic
            if player_stats is None:
                logger.info(f"[{worker_id}]: Player {player_data.name} not found.")
                await player_nf_producer.produce_one(
                    player=NotFoundStruct(
                        metadata=MetaData(version=1, source="hiscore_scraper"),
                        player_data=player_data,
                    )
                )
                continue

            # transform player stats to hiscore data
            scraped_data, error = await transform_player_stats(
                player_stats=player_stats, player=player_data
            )

            if error:
                logger.error(f"[{worker_id}]: Error transforming {player_data.name}.")
                await player_ts_producer.produce_one(player=player)
                continue

            await player_sc_producer.produce_one(scraped_data=scraped_data)
            logger.info(f"[{worker_id}]: {player_data.name} scraped successfully.")
            # print(f"[{worker_id}]: {player_data.name} scraped successfully.")


async def main():
    proxy_manager = ProxyManager(api_key=ProxySettings().PROXY_API_KEY)
    proxies = await proxy_manager.fetch_proxies()

    # initialize kafka producers and consumers
    b_server = KafkaSettings().KAFKA_BOOTSTRAP_SERVERS
    ## consumer
    player_ts_consumer = RepoPlayersToScrapeConsumer(
        bootstrap_servers=b_server, group_id="scraper"
    )
    ## producer
    player_ts_producer = RepoPlayersToScrapeProducer(bootstrap_servers=b_server)
    player_nf_producer = RepoPlayersNotFoundProducer(bootstrap_servers=b_server)
    player_sc_producer = RepoPlayerScrapedProducer(bootstrap_servers=b_server)

    # start kafka producers and consumers
    await player_ts_consumer.start()
    await player_ts_producer.start()
    await player_nf_producer.start()
    await player_sc_producer.start()
    # start workers
    workers = [
        work(
            worker_id=worker_id,
            proxy_manager=proxy_manager,
            player_ts_consumer=player_ts_consumer,
            player_ts_producer=player_ts_producer,
            player_nf_producer=player_nf_producer,
            player_sc_producer=player_sc_producer,
        )
        for worker_id in range(len(proxies))
    ]
    logger.info(f"Starting {len(workers)} workers.")

    await asyncio.gather(*[w for w in workers])


async def run_async():
    await main()


def run():
    asyncio.run(run_async())


if __name__ == "__main__":
    run()
