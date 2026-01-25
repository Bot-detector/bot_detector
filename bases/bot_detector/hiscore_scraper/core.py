import asyncio
import logging
import os
import time
from datetime import date, datetime, timedelta
from typing import Any

import aiohttp
from aiohttp import ClientSession
from bot_detector.kafka import (
    PlayersScrapedProducer,
    PlayersToScrapeConsumer,
    PlayersToScrapeProducer,
    PlayersNotFoundProducer,
)
from bot_detector.kafka import Settings as KafkaSettings
from bot_detector.kafka import ScrapedStruct, NotFoundStruct, ToScrapeStruct
from bot_detector.proxy_manager import ProxyManager
from bot_detector.proxy_manager import Settings as ProxySettings
from bot_detector.structs import (
    HighscoreBaseStruct,
    MetaData,
    PlayerStruct,
)
from osrs.asyncio import Hiscore, HSMode
from osrs.asyncio.osrs.hiscores import PlayerStats
from osrs.exceptions import PlayerDoesNotExist, UnexpectedRedirection
from osrs.utils import RateLimiter
from prometheus_client import Counter, Histogram, start_http_server
from pydantic import ValidationError

logger = logging.getLogger(__name__)

if os.environ.get("ENVIRONMENT") != "test":
    start_http_server(8000)

# Prometheus metrics
total_counter = Counter(
    name="highscore_request_count",
    documentation="Count of request player stats fetches",
    labelnames=["proxy"],
)
success_counter = Counter(
    name="highscore_success_count",
    documentation="Count of successful player stats fetches",
    labelnames=["proxy"],
)
error_counter = Counter(
    name="highscore_error_count",
    documentation="Count of failed player stats fetches",
    labelnames=["proxy"],
)
not_found_counter = Counter(
    name="highscore_not_found_count",
    documentation="Count of players not found",
    labelnames=["proxy"],
)
latency_histogram = Histogram(
    name="highscore_fetch_latency_seconds",
    documentation="Latency of player stats fetches",
    labelnames=["proxy"],
    buckets=(0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0, 20.0, 30.0),
)


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
    session: ClientSession,
    hiscore_instance: Hiscore,
) -> tuple[PlayerStats | None, float | None, str | None]:
    player_stats, error, latency = None, None, None
    try:
        player_stats, latency = await hiscore_instance.get(
            mode=HSMode.OLDSCHOOL,
            player=player.name,
            session=session,
            return_latency=True,
        )
        return player_stats, latency, error
    except PlayerDoesNotExist:
        logger.debug(f"{player.name=} does not exist.")
        return None, None, None
    except UnexpectedRedirection:
        error = f"Unexpected redirection for {player.name=}."
        # logger.error(error)
        return None, None, error
    except (
        aiohttp.ClientResponseError,
        aiohttp.ConnectionTimeoutError,
        aiohttp.ClientConnectorError,
        aiohttp.ServerDisconnectedError,
    ) as e:
        error = f"Client response error: {e}"
        # logger.error(error)
        return None, None, error


async def transform_player_stats(
    player_stats: PlayerStats,
    player: PlayerStruct,
) -> tuple[ScrapedStruct | None, Any | None]:
    player.updated_at = datetime.now()
    player.possible_ban = False
    player.confirmed_ban = False

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
                time_to_live=date.today() + timedelta(days=30),
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
    rate_limiter: RateLimiter,
    player_ts_consumer: PlayersToScrapeConsumer,
    player_ts_producer: PlayersToScrapeProducer,
    player_nf_producer: PlayersNotFoundProducer,
    player_sc_producer: PlayersScrapedProducer,
):
    async with ClientSession() as session:
        while True:
            # get proxy
            proxy = await get_proxy(proxy_manager, worker_id)
            _proxy = proxy.split("@")[1]

            # handle exceptions
            if proxy is None:
                logger.error(f"[{worker_id}]: No proxy available.")
                await asyncio.sleep(10)
                continue

            # get player from kafka
            try:
                start_time = time.perf_counter()
                player = await player_ts_consumer.consume_one()
                total_time = time.perf_counter() - start_time
                logger.debug(f"[{worker_id}]: consume one {total_time:.4f}")
            except ValidationError as e:
                logger.error(e.json())
                continue

            # handle exceptions
            if player is None:
                logger.warning(f"[{worker_id}]: No player available.")
                await asyncio.sleep(10)
                continue

            player_data = player.player_data

            hiscore_instance = Hiscore(
                proxy=proxy,
                rate_limiter=rate_limiter,
            )

            # metric: every time we scrape a player, we increment the counter
            total_counter.labels(proxy=_proxy).inc()

            player_stats, latency, error = await scrape_player(
                player=player_data,
                session=session,
                hiscore_instance=hiscore_instance,
            )

            if latency:
                latency_histogram.labels(proxy=_proxy).observe(latency)
                logger.debug(f"[{worker_id}]: scrape one {latency:.4f}")

            # handle exceptions
            if error:
                error_counter.labels(proxy=_proxy).inc()
                logger.warning(f"[{worker_id}][{player_data.name}]: {error=}")
                await player_ts_producer.produce_one(
                    ToScrapeStruct(
                        metadata=MetaData(version=1, source="hiscore_scraper"),
                        player_data=player,
                    )
                )
                await asyncio.sleep(10)
                continue

            # if player not found, than send to not found topic
            if player_stats is None:
                not_found_counter.labels(proxy=_proxy).inc()
                logger.debug(f"[{worker_id}][{player_data.name}]: not found.")
                player_data.possible_ban = True
                await player_nf_producer.produce_one(
                    NotFoundStruct(
                        metadata=MetaData(version=1, source="hiscore_scraper"),
                        player_data=player_data,
                    )
                )
                continue

            success_counter.labels(proxy=_proxy).inc()

            # transform player stats to hiscore data
            scraped_data, error = await transform_player_stats(
                player_stats=player_stats, player=player_data
            )

            if error:
                logger.error(f"[{worker_id}][{player_data.name}]: Error transforming.")
                await player_ts_producer.produce_one(player=player)
                continue

            await player_sc_producer.produce_one(
                scraped_data, partition_key=str(scraped_data.player_data.id % 10).encode("utf-8")
            )
            logger.debug(f"[{worker_id}][{player_data.name}]: scraped successfully.")


async def main():
    proxy_manager = ProxyManager(api_key=ProxySettings().PROXY_API_KEY)
    proxies = await proxy_manager.fetch_proxies()

    # initialize kafka producers and consumers
    b_server = KafkaSettings().KAFKA_BOOTSTRAP_SERVERS
    ## consumer
    player_ts_consumer = PlayersToScrapeConsumer(
        bootstrap_servers=b_server, group_id="scraper"
    )
    ## producer
    player_ts_producer = PlayersToScrapeProducer(bootstrap_servers=b_server)
    player_nf_producer = PlayersNotFoundProducer(bootstrap_servers=b_server)
    player_sc_producer = PlayersScrapedProducer(bootstrap_servers=b_server)

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
            rate_limiter=RateLimiter(
                calls_per_interval=ProxySettings().MAX_CALLS,
                interval=ProxySettings().INTERVAL,
            ),
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
    # test if cicd runs
