import asyncio
import logging
import os
from datetime import datetime

import aiohttp
from aiohttp import ClientSession
from bot_detector.event_queue.adapters.kafka import (
    KafkaConfig,
    KafkaConsumerConfig,
    KafkaProducerConfig,
    KafkaSettings,
)
from bot_detector.event_queue.core import Queue, QueueProducer
from bot_detector.event_queue.factory import QueueFactory
from bot_detector.event_queue.structs import NotFoundStruct, ScrapedStruct
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
) -> str | None:
    proxy, error = await proxy_manager.get_proxy(worker_id)

    if error:
        logger.error(f"[{worker_id}]: {error}")
        return None

    if isinstance(proxy, list):
        logger.error(f"[{worker_id}]: Expected single proxy, got list.")
        return None

    return proxy


async def scrape_player(
    player: PlayerStruct,
    session: ClientSession,
    runemetrics_instance: RuneMetrics,
) -> tuple[PlayerStruct | None, float | None, str | None]:
    player_data, latency, error = None, None, None
    try:
        player_data, latency = await runemetrics_instance.get(
            player_name=player.name,
            session=session,
            return_latency=True,
        )
        return player_data, latency, error
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


async def update_player(
    player_data: PlayerStruct,
    runemetrics_response: RuneMetricsResponse,
) -> PlayerStruct:
    player_data.updated_at = datetime.now()
    player_data.possible_ban = 1
    player_data.confirmed_player = 0

    if runemetrics_response.error is None:
        player_data.label_jagex = 0
        return player_data

    _error = runemetrics_response.error.error
    player_update_errors.labels(error_type=_error).inc()

    match _error:
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
    player_nf_queue: Queue[NotFoundStruct],
    player_sc_producer: QueueProducer[ScrapedStruct],
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
                player, error = await player_nf_queue.consume_one()
            except ValidationError as e:
                error = e.json()
                logger.error(error)
                continue
            if error:
                logger.error(f"[{worker_id}]: {error}")
                await asyncio.sleep(10)
                continue

            if player is None:
                logger.error(f"[{worker_id}]: No player available.")
                await asyncio.sleep(10)
                continue

            player_data = player.player_data

            runemetrics_instance = RuneMetrics(
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
                produce_error = await player_nf_queue.put([player])
                if produce_error:
                    logger.error(
                        f"[{worker_id}]: Failed to requeue player: {produce_error}"
                    )
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
                produce_error = await player_nf_queue.put([player])
                if produce_error:
                    logger.error(
                        f"[{worker_id}]: Failed to requeue player: {produce_error}"
                    )
                continue

            # push data to kafka
            success_counter.labels(proxy=_proxy).inc()
            produce_error = await player_sc_producer.put([scraped_data])
            if produce_error:
                logger.error(
                    f"[{worker_id}]: Failed to produce scraped player: {produce_error}"
                )
                continue
            logger.debug(
                f"[{worker_id}][{player_data.name}]: {player_data.label_jagex=}"
            )


async def main():
    proxy_manager = ProxyManager(api_key=ProxySettings().PROXY_API_KEY)
    proxies = await proxy_manager.fetch_proxies()

    # initialize kafka producers and consumers
    b_server = KafkaSettings().bootstrap_servers

    player_nf_queue = QueueFactory.create_queue(
        model=NotFoundStruct,
        queue_type="queue",
        backend_type="kafka",
        config=KafkaConfig(
            topic="players.not_found",
            bootstrap_servers=b_server,
            producer=True,
            consumer=True,
            producer_config=KafkaProducerConfig(partition_key_fn=None),
            consumer_config=KafkaConsumerConfig(group_id="runemetrics_scraper"),
        ),
    )
    player_sc_producer = QueueFactory.create_queue(
        model=ScrapedStruct,
        queue_type="producer",
        backend_type="kafka",
        config=KafkaConfig(
            topic="players.scraped",
            bootstrap_servers=b_server,
            producer=True,
            producer_config=KafkaProducerConfig(
                partition_key_fn=lambda message: str(message.player_data.id % 10)
            ),
        ),
    )
    for queue in (player_nf_queue, player_sc_producer):
        if isinstance(queue, Exception):
            raise queue

    await player_nf_queue.start()
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
                player_nf_queue=player_nf_queue,
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
