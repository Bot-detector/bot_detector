import asyncio
import logging
import os
from datetime import datetime

import aiohttp
from aiohttp import ClientSession
from bot_detector.kafka import (
    PlayersScrapedProducer,
    PlayersNotFoundConsumer,
    PlayersNotFoundProducer,
)
from bot_detector.kafka import Settings as KafkaSettings
from bot_detector.kafka import NotFoundStruct, ScrapedStruct
from bot_detector.proxy_manager import ProxyManager
from bot_detector.proxy_manager import Settings as ProxySettings
from bot_detector.runemetrics_api import RuneMetrics, RuneMetricsResponse
from bot_detector.runemetrics_api.exceptions import UnexpectedRedirection
from bot_detector.structs import MetaData, PlayerStruct
from osrs.utils import RateLimiter
from prometheus_client import Counter, Histogram, start_http_server
from pydantic import ValidationError

logger = logging.getLogger(__name__)

if os.environ.get("ENVIRONMENT") != "test":
    start_http_server(8000)

# Prometheus metrics
total_counter = Counter(
    name="rune_metrics_request",
    documentation="Count of request player stats fetches",
    labelnames=["proxy"],
)
success_counter = Counter(
    name="rune_metrics_success",
    documentation="Successful RuneMetrics requests",
    labelnames=["proxy"],
)
error_counter = Counter(
    name="rune_metrics_errors",
    documentation="Errors in RuneMetrics requests",
    labelnames=["proxy"],
)
latency_histogram = Histogram(
    name="rune_metrics_latency",
    documentation="Latency of RuneMetrics requests",
    labelnames=["proxy"],
    buckets=(
        0.05,
        0.075,
        0.1,
        0.25,
        0.5,
        0.75,
        1.0,
        2.5,
        5.0,
        7.5,
        10.0,
        20.0,
        30.0,
    ),
)

player_update_errors = Counter(
    "player_update_errors_total",
    "Count of errors during player update by error type",
    ["error_type"],
)


async def get_proxy(
    proxy_manager: ProxyManager,
    worker_id: int,
) -> str:
    proxy, error = await proxy_manager.get_proxy(worker_id)
            if error:
                error_counter.labels(proxy=_proxy).inc()
                logger.warning(f"[{worker_id}][{player_data.name}]: {error=}")
                await player_nf_producer.produce_one(
                    NotFoundStruct(
                        metadata=MetaData(version=1, source="runemetrics_scraper"),
                        player_data=player_data,
                    )
                )
                await asyncio.sleep(10)
                continue

            # handle exceptions
            if player is None:
                logger.error(f"[{worker_id}]: No player available.")
                await asyncio.sleep(10)
                continue

    player_data = player_data

    hiscore_instance = Hiscore(
        proxy=proxy,
        rate_limiter=rate_limiter,
    )

            # metric: every time we scrape a player, we increment the counter
            total_counter.labels(proxy=_proxy).inc()

            runemetrics_response, latency, error = await scrape_player(
                player=player_data,
                session=session,
                runemetrics_instance=runemetrics_instance,
            )

            if latency:
                latency_histogram.labels(proxy=_proxy).observe(latency)

            # handle exceptions
            if error:
                error_counter.labels(proxy=_proxy).inc()
                logger.warning(f"[{worker_id}][{player_data.name}]: {error=}")
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
            success_counter.labels(proxy=_proxy).inc()
            await player_sc_producer.produce_one(
                scraped_data, partition_key=str(scraped_data.player_data.id % 10).encode("utf-8")
            )
            logger.debug(
                f"[{worker_id}][{player_data.name}]: {player_data.label_jagex=}"
            )


async def main():
    proxy_manager = ProxyManager(api_key=ProxySettings().PROXY_API_KEY)
    proxies = await proxy_manager.fetch_proxies()

    # initialize kafka producers and consumers
    b_server = KafkaSettings().KAFKA_BOOTSTRAP_SERVERS

    ## consumer
    player_nf_consumer = PlayersNotFoundConsumer(
        bootstrap_servers=b_server, group_id="runemetrics_scraper"
    )

    ## producer
    player_nf_producer = PlayersNotFoundProducer(bootstrap_servers=b_server)
    player_sc_producer = PlayersScrapedProducer(bootstrap_servers=b_server)

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
