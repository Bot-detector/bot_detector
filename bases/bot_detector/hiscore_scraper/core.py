import asyncio
import logging
from datetime import date, datetime, timedelta

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
from bot_detector.event_queue.structs import (
    NotFoundStruct,
    ScrapedStruct,
    ToScrapeStruct,
)
from bot_detector.osrs_hs_api import HiscoreOldSchoolAPI
from bot_detector.osrs_hs_api.exceptions import Err, Ok, PlayerDoesNotExist
from bot_detector.osrs_hs_api.structs import PlayerStats
from bot_detector.proxy_manager import ProxyManager
from bot_detector.proxy_manager import Settings as ProxySettings
from bot_detector.rate_limiter import RateLimiter
from bot_detector.retry_tracker import RetryTracker
from bot_detector.structs import (
    HighscoreBaseStruct,
    MetaData,
    PlayerStruct,
)
from pydantic import ValidationError

from .metrics import (
    error_counter,
    latency_histogram,
    not_found_counter,
    retry_counter,
    retry_delay_histogram,
    retry_histogram,
    success_counter,
    total_counter,
)

logger = logging.getLogger(__name__)


async def produce_player_to_scrape(
    player_ts_queue: Queue[ToScrapeStruct],
    player: PlayerStruct,
):
    error = None
    retries = 0
    MAX_RETRIES = 3
    while retries < MAX_RETRIES:
        to_scrape_struct = ToScrapeStruct(
            metadata=MetaData(version=1, source="hiscore_scraper"),
            player_data=player,
        )
        error = await player_ts_queue.put([to_scrape_struct])
        if not error:
            return None
        retries += 1
        logger.error(f"Failed to produce player to scrape (attempt {retries}): {error}")
        await asyncio.sleep(2**retries)  # Exponential backoff
    return Exception(
        f"Failed to produce player to scrape after {MAX_RETRIES} attempts: {error}"
    )


async def produce_not_found(
    player_nf_producer: QueueProducer[NotFoundStruct],
    player: PlayerStruct,
):
    error = None
    retries = 0
    MAX_RETRIES = 3
    while retries < MAX_RETRIES:
        not_found_struct = NotFoundStruct(
            metadata=MetaData(version=1, source="hiscore_scraper"),
            player_data=player,
        )
        error = await player_nf_producer.put([not_found_struct])
        if not error:
            return None
        retries += 1
        logger.error(f"Failed to produce not found (attempt {retries}): {error}")
        await asyncio.sleep(2**retries)  # Exponential backoff
    return Exception(
        f"Failed to produce not found after {MAX_RETRIES} attempts: {error}"
    )


async def produce_player_scraped(
    player_sc_producer: QueueProducer[ScrapedStruct],
    scraped_data: ScrapedStruct,
):
    error = None
    retries = 0
    MAX_RETRIES = 3
    while retries < MAX_RETRIES:
        error = await player_sc_producer.put([scraped_data])
        if not error:
            return None
        retries += 1
        logger.error(f"Failed to produce scraped data (attempt {retries}): {error}")
        await asyncio.sleep(2**retries)  # Exponential backoff
    return Exception(
        f"Failed to produce scraped data after {MAX_RETRIES} attempts: {error}"
    )


async def scrape_player(
    player: PlayerStruct,
    session: ClientSession,
    api: HiscoreOldSchoolAPI,
    proxy: str,
) -> tuple[PlayerStats | None, Exception | None]:
    """
    Scrape player stats from hiscores.
    Returns a tuple of (PlayerStats | None, Exception | None).
    Caller handles error-based logic (retry, not_found, proxy refresh).
    """
    result = await api.get(player=player.name, session=session, proxy=proxy)

    if isinstance(result, Ok):
        latency_histogram.labels(proxy=proxy).observe(result.latency)
        return result.value, None
    elif isinstance(result, Err):
        return None, result.error
    else:
        return None, Exception("Unexpected result type from scrape_player")


async def transform_player_stats(
    player_stats: PlayerStats,
    player: PlayerStruct,
    player_ts_producer: Queue[ToScrapeStruct],
) -> ScrapedStruct | None:
    player.updated_at = datetime.now()
    player.possible_ban = False
    player.confirmed_ban = False
    player.label_jagex = 0

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
        return hiscore_data
    except ValidationError as e:
        error = e.json()
        logger.error(error)
        error = await produce_player_to_scrape(player_ts_producer, player)
        if error:
            logger.error(f"Failed to requeue player after transform failure: {error}")
        return None


async def handle_retry(
    retry_tracker: RetryTracker,
    worker_id: int,
    proxy: str,
):
    """
    Handle retry logic: update metrics and sleep with backoff delay.

    Args:
        retry_tracker: RetryTracker instance.
        worker_id: Worker identifier.
        proxy: Proxy address for metrics labels.
    """
    _proxy = proxy.split("@")[1]
    retry_tracker.record_attempt(worker_id, success=False)
    delay = retry_tracker.get_backoff_delay(worker_id)
    retry_count = retry_tracker.get_retry_count(worker_id)

    # metrics
    retry_counter.labels(proxy=_proxy).inc()
    retry_histogram.labels(proxy=_proxy).observe(retry_count)
    retry_delay_histogram.labels(proxy=_proxy).observe(delay)

    logger.warning(f"[{worker_id}]: backing off {delay:.2f}s")
    await asyncio.sleep(delay)


async def get_proxy(
    worker_id: int,
    proxy_manager: ProxyManager,
) -> str | None:
    proxy, error = await proxy_manager.get_proxy(worker_id)
    if isinstance(proxy, list):
        logger.error(f"Worker {worker_id}: Proxy is a list: {proxy}")
        return None
    elif proxy is None:
        logger.error(f"Worker {worker_id}: No proxy available.")
        return None
    elif error:
        logger.error(f"Worker {worker_id}: Error getting proxy: {error}")
        _error = f"Worker {worker_id}: {error}"
        logger.error(_error)
        return None
    return proxy


async def get_player_to_scrape(
    worker_id: int,
    player_ts_queue: Queue[ToScrapeStruct],
) -> ToScrapeStruct | None:
    result = await player_ts_queue.get_one()
    if isinstance(result, Exception):
        logger.error(f"[{worker_id}]: Error consuming player to scrape: {result}")
        return None
    if result is None:
        logger.warning(f"[{worker_id}]: No player available.")
        return None
    commit_error = await player_ts_queue.commit()
    if commit_error:
        logger.error(
            f"[{worker_id}]: Error committing player to scrape offset: {commit_error}"
        )
        return None
    return result


async def work(
    worker_id: int,
    proxy_manager: ProxyManager,
    player_ts_queue: Queue[ToScrapeStruct],
    player_nf_producer: QueueProducer[NotFoundStruct],
    player_sc_producer: QueueProducer[ScrapedStruct],
):
    retry_tracker = RetryTracker(base_delay=1.0, max_delay=300.0, decay_window=300.0)
    rate_limiter = RateLimiter(
        calls_per_interval=ProxySettings().MAX_CALLS,  # type: ignore
        interval=ProxySettings().INTERVAL,  # type: ignore
    )

    async with ClientSession(
        headers={"User-Agent": "http://osrsbotdetector.com"}
    ) as session:
        while True:
            proxy = await get_proxy(worker_id, proxy_manager)
            if proxy is None:
                await asyncio.sleep(10)
                continue

            _proxy = proxy.split("@")[1]

            # get player from kafka
            player_to_scrape = await get_player_to_scrape(worker_id, player_ts_queue)
            if player_to_scrape is None:
                await asyncio.sleep(10)
                continue

            player_data = player_to_scrape.player_data

            api = HiscoreOldSchoolAPI(rate_limiter=rate_limiter)

            # metric: every time we scrape a player, we increment the counter
            total_counter.labels(proxy=_proxy).inc()

            player_stats, scrape_error = await scrape_player(
                player=player_data,
                session=session,
                api=api,
                proxy=proxy,
            )

            if scrape_error:
                log_prefix = f"[{worker_id}][{player_data.name}]"

                if isinstance(scrape_error, PlayerDoesNotExist):
                    not_found_counter.labels(proxy=_proxy).inc()
                    player_data.possible_ban = True
                    err = await produce_not_found(player_nf_producer, player_data)
                    if err:
                        logger.error(f"{log_prefix}:{err}")
                    continue
                if isinstance(scrape_error, aiohttp.ClientHttpProxyError):
                    if scrape_error.status == 407:
                        logger.warning(f"{log_prefix}: Rotating proxies.")
                        await proxy_manager.rotate_proxies()
                        await asyncio.sleep(10)

                logger.warning(f"{log_prefix}: {scrape_error=}")
                error_counter.labels(proxy=_proxy).inc()
                err = await produce_player_to_scrape(player_ts_queue, player_data)
                if err:
                    logger.error(f"{log_prefix}: {err}")
                await handle_retry(retry_tracker, worker_id, proxy)
                continue

            success_counter.labels(proxy=_proxy).inc()

            # transform player stats to hiscore data
            assert player_stats is not None  # for mypy
            scraped_data = await transform_player_stats(
                player_stats=player_stats,
                player=player_data,
                player_ts_producer=player_ts_queue,
            )

            if scraped_data is None:
                await handle_retry(retry_tracker, worker_id, proxy)
                continue

            # Successful scrape - reset retry counter
            retry_tracker.record_attempt(worker_id, success=True)

            error = await produce_player_scraped(player_sc_producer, scraped_data)
            logger_prefix = f"[{worker_id}][{player_data.name}]"
            if error:
                logger.error(f"{logger_prefix}: {error}")
                await produce_player_to_scrape(player_ts_queue, player_data)
                continue

            logger.debug(f"{logger_prefix}: scraped successfully.")


async def main():
    proxy_manager = ProxyManager(api_key=ProxySettings().PROXY_API_KEY)  # type: ignore
    proxies = await proxy_manager.fetch_proxies()

    # initialize kafka producers and consumers
    b_server = KafkaSettings().bootstrap_servers
    player_ts_queue = QueueFactory.create_queue(
        model=ToScrapeStruct,
        queue_type="queue",
        backend_type="kafka",
        config=KafkaConfig(
            topic="players.to_scrape",
            bootstrap_servers=b_server,
            producer=True,
            consumer=True,
            producer_config=KafkaProducerConfig(partition_key_fn=None),
            consumer_config=KafkaConsumerConfig(group_id="scraper"),
        ),
    )
    player_nf_producer = QueueFactory.create_queue(
        model=NotFoundStruct,
        queue_type="producer",
        backend_type="kafka",
        config=KafkaConfig(
            topic="players.not_found",
            bootstrap_servers=b_server,
            producer=True,
            producer_config=KafkaProducerConfig(partition_key_fn=None),
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
    for queue in (player_ts_queue, player_nf_producer, player_sc_producer):
        if isinstance(queue, Exception):
            raise queue

    assert isinstance(player_ts_queue, Queue)
    assert isinstance(player_nf_producer, QueueProducer)
    assert isinstance(player_sc_producer, QueueProducer)

    await player_ts_queue.start()
    await player_nf_producer.start()
    await player_sc_producer.start()
    # start workers
    workers = [
        work(
            worker_id=worker_id,
            proxy_manager=proxy_manager,
            player_ts_queue=player_ts_queue,
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
