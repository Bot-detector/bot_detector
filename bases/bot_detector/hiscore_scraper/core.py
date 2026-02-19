import asyncio
import logging
from datetime import date, datetime, timedelta

import aiohttp
from aiohttp import ClientSession
from bot_detector.event_queue.adapters.kafka import (
    KafkaConfig,
    KafkaConsumerConfig,
    KafkaProducerConfig,
)
from bot_detector.event_queue.adapters.kafka import KafkaSettings
from bot_detector.event_queue.core import Queue, QueueProducer
from bot_detector.event_queue.factory import QueueFactory
from bot_detector.event_queue.structs import (
    NotFoundStruct,
    ScrapedStruct,
    ToScrapeStruct,
)
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
from .retry_tracker import RetryTracker

logger = logging.getLogger(__name__)


async def scrape_player(
    worker_id: int,
    player: PlayerStruct,
    session: ClientSession,
    hiscore_instance: Hiscore,
    proxy: str,
    player_nf_producer: QueueProducer[NotFoundStruct],
    player_ts_producer: Queue[ToScrapeStruct],
) -> tuple[PlayerStats | None, bool]:
    """
    Scrape player stats from hiscores.
    Returns a tuple of (PlayerStats | None, bool) where the bool indicates
    whether to retry scraping the player.
    """
    try:
        hiscore_data = await hiscore_instance.get(
            mode=HSMode.OLDSCHOOL,
            player=player.name,
            session=session,
            return_latency=True,
        )
        if isinstance(hiscore_data, tuple):
            player_stats, latency = hiscore_data
            latency_histogram.labels(proxy=proxy).observe(latency)
        else:
            player_stats = hiscore_data
        return player_stats, False
    except PlayerDoesNotExist:
        not_found_counter.labels(proxy=proxy).inc()
        logger.debug(f"[{worker_id}][{player.name}]: not found.")
        player.possible_ban = True
        await player_nf_producer.produce_one(
            NotFoundStruct(
                metadata=MetaData(version=1, source="hiscore_scraper"),
                player_data=player,
            )
        )
        return None, False
    except UnexpectedRedirection as e:
        error_counter.labels(proxy=proxy).inc()
        logger.warning(f"[{worker_id}][{player.name}]: {e=}")
        await player_ts_producer.produce_one(
            ToScrapeStruct(
                metadata=MetaData(version=1, source="hiscore_scraper"),
                player_data=player,
            )
        )
        return None, True
    except (
        aiohttp.ClientResponseError,
        aiohttp.ConnectionTimeoutError,
        aiohttp.ClientConnectorError,
        aiohttp.ServerDisconnectedError,
        asyncio.TimeoutError,
    ) as e:
        error_counter.labels(proxy=proxy).inc()
        logger.warning(f"[{worker_id}][{player.name}]: {e=}")
        await player_ts_producer.produce_one(
            ToScrapeStruct(
                metadata=MetaData(version=1, source="hiscore_scraper"),
                player_data=player,
            )
        )
        return None, True


async def transform_player_stats(
    player_stats: PlayerStats,
    player: PlayerStruct,
    player_ts_producer: Queue[ToScrapeStruct],
) -> ScrapedStruct | None:
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
        return hiscore_data
    except ValidationError as e:
        error = e.json()
        logger.error(error)
        await player_ts_producer.produce_one(
            ToScrapeStruct(
                metadata=MetaData(version=1, source="hiscore_scraper"),
                player_data=player,
            )
        )
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
    player_to_scrape, error = await player_ts_queue.consume_one()
    if error:
        logger.error(f"[{worker_id}]: Error consuming player to scrape: {error}")
        return None
    if player_to_scrape is None:
        logger.warning(f"[{worker_id}]: No player available.")
        return None
    return player_to_scrape


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

            hiscore_instance = Hiscore(
                proxy=proxy,
                rate_limiter=rate_limiter,
            )

            # metric: every time we scrape a player, we increment the counter
            total_counter.labels(proxy=_proxy).inc()

            player_stats, retry = await scrape_player(
                player=player_data,
                session=session,
                hiscore_instance=hiscore_instance,
                proxy=_proxy,
                worker_id=worker_id,
                player_nf_producer=player_nf_producer,
                player_ts_producer=player_ts_queue,
            )
            if player_stats is None:
                if retry:
                    await handle_retry(retry_tracker, worker_id, proxy)
                continue

            success_counter.labels(proxy=_proxy).inc()

            # transform player stats to hiscore data
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

            partition_key = str(scraped_data.player_data.id % 10).encode("utf-8")
            await player_sc_producer.produce_one(
                message=scraped_data,
                partition_key=partition_key,
            )
            logger.debug(f"[{worker_id}][{player_data.name}]: scraped successfully.")


async def main():
    proxy_manager = ProxyManager(api_key=ProxySettings().PROXY_API_KEY)  # type: ignore
    proxies = await proxy_manager.fetch_proxies()

    # initialize kafka producers and consumers
    b_server = KafkaSettings().KAFKA_BOOTSTRAP_SERVERS
    player_ts_queue = QueueFactory.create_queue(
        model=ToScrapeStruct,
        queue_type="queue",
        backend_type="kafka",
        config=KafkaConfig(
            topic="players.to_scrape",
            bootstrap_servers=b_server,
            producer=True,
            consumer=True,
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
