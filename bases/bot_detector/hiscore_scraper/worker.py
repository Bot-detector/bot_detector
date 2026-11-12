import asyncio
import logging

import aiohttp
from bot_detector.event_queue.core import Queue, QueueProducer
from bot_detector.event_queue.structs import (
    NotFoundStruct,
    ScrapedStruct,
    ToScrapeStruct,
)
from bot_detector.hiscore_scraper.metrics import (
    error_counter,
    not_found_counter,
    on_rate_limit_wait,
    retry_counter,
    retry_delay_histogram,
    retry_histogram,
    success_counter,
    total_counter,
)
from bot_detector.hiscore_scraper.producers import (
    produce_not_found,
    produce_player_scraped,
    produce_player_to_scrape,
)
from bot_detector.hiscore_scraper.scrape import scrape_player, transform_player_stats
from bot_detector.hiscore_scraper.session import build_session
from bot_detector.osrs_hs_api import HiscoreOldSchoolAPI
from bot_detector.osrs_hs_api.exceptions import PlayerDoesNotExist
from bot_detector.proxy_manager import ProxyManager
from bot_detector.proxy_manager import Settings as ProxySettings
from bot_detector.rate_limiter import RateLimiter, Window
from bot_detector.retry_tracker import RetryTracker

logger = logging.getLogger(__name__)

# cooldown after rotating proxies: give the fresh pool a moment before
# the next scrape attempt
ROTATE_COOLDOWN_S = 10.0


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
    proxy_settings = ProxySettings()  # type: ignore[call-arg]
    rate_limiter = RateLimiter(
        windows=[
            Window(
                name="minute",
                count=proxy_settings.MAX_CALLS,
                interval_ms=proxy_settings.INTERVAL_MS,
            ),
            Window(
                name="second",
                count=proxy_settings.MAX_CALLS_PER_SECOND,
                interval_ms=proxy_settings.SECOND_INTERVAL_MS,
            ),
        ],
        on_wait=on_rate_limit_wait,
    )
    api = HiscoreOldSchoolAPI(rate_limiter=rate_limiter)

    async with build_session() as session:
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
                        await asyncio.sleep(ROTATE_COOLDOWN_S)

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
