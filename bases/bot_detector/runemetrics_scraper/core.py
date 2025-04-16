import asyncio
import logging
from datetime import datetime

import aiohttp
from aiohttp import ClientSession
from bot_detector.kafka import Settings as KafkaSettings
from bot_detector.kafka.repositories import (
    RepoPlayerScrapedProducer,
    RepoPlayersNotFoundConsumer,
    RepoPlayersNotFoundProducer,
)
from bot_detector.proxy_manager import ProxyManager
from bot_detector.proxy_manager import Settings as ProxySettings
from bot_detector.runemetrics_api import RuneMetrics, RuneMetricsResponse
from bot_detector.runemetrics_api.exceptions import UnexpectedRedirection
from bot_detector.structs import MetaData, PlayerStruct, ScrapedStruct
from osrs.utils import RateLimiter
from pydantic import ValidationError

logger = logging.getLogger(__name__)


async def get_proxy(
    proxy_manager: ProxyManager,
    worker_id: int,
) -> str:
    proxy, error = await proxy_manager.get_proxy(worker_id)
    if error:
        logger.error(f"[{worker_id}]: {error}")
        return None
    return proxy


async def scrape_player(
    player: PlayerStruct,
    session: ClientSession,
    runemetrics_instance: RuneMetrics,
) -> tuple[PlayerStruct | None, str | None]:
    player_data, error = None, None
    try:
        player_data = await runemetrics_instance.get(
            player_name=player.name,
            session=session,
        )
        return player_data, error
    except UnexpectedRedirection:
        error = f"Unexpected redirection for {player.name=}."
        logger.error(error)
        return None, error
    except (
        aiohttp.ClientResponseError,
        aiohttp.ConnectionTimeoutError,
        aiohttp.ClientConnectorError,
    ) as e:
        error = f"Client response error: {e}"
        logger.error(error)
        return None, error


async def update_player(
    player_data: PlayerStruct,
    runemetrics_response: RuneMetricsResponse,
):
    player_data.updated_at = datetime.now()
    player_data.possible_ban = 1
    player_data.confirmed_player = 0

    match runemetrics_response.error:
        # username is not associated to an account
        case "NO_PROFILE":
            player_data.label_jagex = 1
        # account is perm banned
        case "NOT_A_MEMBER":
            player_data.label_jagex = 2
        # runemetrics is set to private. either they're too low level or they're banned.
        case "PROFILE_PRIVATE":
            player_data.label_jagex = 3
        case _:
            # account is active, probably just too low stats for hiscores
            player_data.label_jagex = 0

    return player_data


async def work(
    worker_id: int,
    proxy_manager: ProxyManager,
    rate_limiter: RateLimiter,
    player_nf_consumer: RepoPlayersNotFoundConsumer,
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
                player = await player_nf_consumer.consume_one()
            except ValidationError as e:
                error = e.json()
                logger.error(error)
                continue

            # handle exceptions
            if player is None:
                logger.error(f"[{worker_id}]: No player available.")
                await asyncio.sleep(10)
                continue

            player_data = player.player_data

            runemetrics_instance = RuneMetrics(
                proxy=proxy,
                rate_limiter=rate_limiter,
            )

            runemetrics_response, error = await scrape_player(
                player=player_data,
                session=session,
                runemetrics_instance=runemetrics_instance,
            )
            # handle exceptions
            if error:
                logger.error(f"[{worker_id}][{player_data.name}]: {error=}")
                await player_nf_producer.produce_one(player=player)
                await asyncio.sleep(10)
                continue

            # update player data
            player_data = await update_player(
                player_data=player_data,
                runemetrics_response=runemetrics_response,
            )
            # create hiscore data
            try:
                scraped_data = ScrapedStruct(
                    metadata=MetaData(version=1, source="runemetrics_scraper"),
                    player_data=player_data,
                    highscore_data=None,
                )
            except ValidationError as e:
                error = e.json()
                logger.error(error)
                await player_nf_producer.produce_one(player=player)
                continue

            # push data to kafka
            await player_sc_producer.produce_one(scraped_data=scraped_data)
            logger.debug(
                f"[{worker_id}][{player_data.name}]: {player_data.label_jagex=}"
            )


async def main():
    proxy_manager = ProxyManager(api_key=ProxySettings().PROXY_API_KEY)
    proxies = await proxy_manager.fetch_proxies()

    # initialize kafka producers and consumers
    b_server = KafkaSettings().KAFKA_BOOTSTRAP_SERVERS

    ## consumer
    player_nf_consumer = RepoPlayersNotFoundConsumer(
        bootstrap_servers=b_server, group_id="runemetrics_scraper"
    )

    ## producer
    player_nf_producer = RepoPlayersNotFoundProducer(bootstrap_servers=b_server)
    player_sc_producer = RepoPlayerScrapedProducer(bootstrap_servers=b_server)

    # start kafka producers and consumers
    await player_nf_consumer.start()
    await player_nf_producer.start()
    await player_sc_producer.start()

    # start workers
    workers = [
        asyncio.create_task(
            work(
                worker_id=worker_id,
                proxy_manager=proxy_manager,
                rate_limiter=RateLimiter(
                    calls_per_interval=ProxySettings().MAX_CALLS,
                    interval=ProxySettings().INTERVAL,
                ),
                player_nf_consumer=player_nf_consumer,
                player_nf_producer=player_nf_producer,
                player_sc_producer=player_sc_producer,
            )
        )
        for worker_id in range(len(proxies))
    ]

    logger.info(f"Starting {len(workers)} workers.")

    await asyncio.gather(*workers)


async def run_async():
    await main()


def run():
    asyncio.run(run_async())


if __name__ == "__main__":
    run()
