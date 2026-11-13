import asyncio
import logging

import aiohttp
from aiohttp import ClientSession
from bot_detector.event_queue.structs import ToScrapeStruct
from bot_detector.hiscore_scraper.errors import dump_error
from bot_detector.hiscore_scraper.flow.structs import FetchResult
from bot_detector.hiscore_scraper.proxy_pool.runtime import ProxyRuntime
from bot_detector.hiscore_scraper.proxy_pool.service import (
    get_proxy_list,
    record_failure,
)
from bot_detector.hiscore_scraper.scraping.metrics import (
    error_counter,
    success_counter,
    total_counter,
)
from bot_detector.hiscore_scraper.scraping.service import proxy_label, scrape_player
from bot_detector.osrs_hs_api.exceptions import PlayerDoesNotExist
from bot_detector.structs import PlayerStruct
from bot_detector.wide_event import WideEventLogger

logger = logging.getLogger(__name__)
wide_event = WideEventLogger()


def _force_log() -> None:
    wide_event.add({"force_log": True})


def _emit() -> None:
    """Emits one wide event per fetch attempt.

    Missing proxies log at error, scrape failures at warning; the
    remaining outcomes log at info when forced or sampled.
    """
    ctx = wide_event.get()
    force_log = bool(ctx.pop("force_log", False))
    if ctx.get("outcome") == "no_proxies":
        logger.error(ctx)
    elif ctx.get("outcome") == "error":
        logger.warning(ctx)
    elif force_log:
        ctx.update({"log_reason": "force"})
        logger.info(ctx)
    elif wide_event.sample():
        ctx.update({"log_reason": "sample"})
        logger.info(ctx)


# cooldown after rotating proxies: give the fresh pool a moment before
# the next scrape attempt
ROTATE_COOLDOWN_S = 10.0

NO_PROXY_SLEEP_S = 10.0


async def fetch(
    fetcher_id: int,
    runtime: ProxyRuntime,
    task_queue: asyncio.Queue[ToScrapeStruct],
    results_queue: asyncio.Queue[FetchResult],
    session: ClientSession,
):
    """Fetch stage: pulls players from task_queue, scrapes, ships results.

    Pure I/O: every slow part (rate-limit waits, proxy cooldowns, retry
    backoff, HTTP latency) stalls only this fetcher's slot. Outcome
    branching happens here where it is known; Kafka side effects
    (requeues, not_found) belong to the processor stage. Each attempt
    emits one wide event (outcome, proxy, dumped error, backoff).
    """
    while True:
        player_to_scrape = await task_queue.get()
        player_data: PlayerStruct = player_to_scrape.player_data
        token = wide_event.set({})
        try:
            wide_event.add(
                {
                    "fetcher": fetcher_id,
                    "player": {"id": player_data.id, "name": player_data.name},
                }
            )

            proxies = await get_proxy_list(runtime.proxy_manager)
            if not proxies:
                wide_event.add({"outcome": "no_proxies"})
                await task_queue.put(player_to_scrape)
                await asyncio.sleep(NO_PROXY_SLEEP_S)
                continue

            # sticky assignment: fetcher i keeps proxy index i, modulo the
            # current pool size (the list is re-read each iteration so
            # rotations are picked up without restarting)
            proxy = proxies[fetcher_id % len(proxies)]
            _proxy = proxy_label(proxy)
            wide_event.add({"proxy": _proxy})

            total_counter.labels(proxy=_proxy).inc()

            player_stats, scrape_error = await scrape_player(
                player=player_data,
                session=session,
                api=runtime.api(proxy),
                proxy=proxy,
            )

            if scrape_error is None:
                assert player_stats is not None  # for mypy
                success_counter.labels(proxy=_proxy).inc()
                tracker, tracker_id = runtime.tracker(proxy)
                tracker.record_attempt(tracker_id, success=True)
                wide_event.add({"outcome": "success"})
                await results_queue.put(
                    FetchResult(player=player_data, proxy=proxy, stats=player_stats)
                )
                continue

            if isinstance(scrape_error, PlayerDoesNotExist):
                # an outcome, not an error: no error counter, no backoff
                wide_event.add({"outcome": "not_found"})
                await results_queue.put(
                    FetchResult(player=player_data, proxy=proxy, error=scrape_error)
                )
                continue

            # 407 from the proxy: rotate the pool and let it settle, then
            # fall through to the generic error path
            if isinstance(scrape_error, aiohttp.ClientHttpProxyError):
                if scrape_error.status == 407:
                    logger.warning(f"[fetcher-{fetcher_id}]: Rotating proxies.")
                    wide_event.add({"proxy_rotated": True})
                    await runtime.proxy_manager.rotate_proxies()
                    await asyncio.sleep(ROTATE_COOLDOWN_S)

            error_counter.labels(proxy=_proxy).inc()
            wide_event.add(
                {"outcome": "error", "scrape_error": dump_error(scrape_error)}
            )
            await results_queue.put(
                FetchResult(player=player_data, proxy=proxy, error=scrape_error)
            )
            delay = record_failure(runtime, proxy)
            wide_event.add({"backoff_seconds": round(delay, 2)})
            await asyncio.sleep(delay)
        finally:
            _emit()
            wide_event.reset(token)
