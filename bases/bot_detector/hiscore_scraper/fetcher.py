import asyncio
import logging

import aiohttp
from aiohttp import ClientSession
from bot_detector.event_queue.structs import ToScrapeStruct
from bot_detector.hiscore_scraper.errors import dump_error
from bot_detector.hiscore_scraper.metrics import (
    error_counter,
    on_rate_limit_wait,
    retry_counter,
    retry_delay_histogram,
    retry_histogram,
    success_counter,
    total_counter,
)
from bot_detector.hiscore_scraper.scrape import proxy_label, scrape_player
from bot_detector.hiscore_scraper.structs import FetchResult
from bot_detector.osrs_hs_api import HiscoreOldSchoolAPI
from bot_detector.osrs_hs_api.exceptions import PlayerDoesNotExist
from bot_detector.proxy_manager import ProxyManager
from bot_detector.proxy_manager import Settings as ProxySettings
from bot_detector.rate_limiter import RateLimiter, Window
from bot_detector.retry_tracker import RetryTracker
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


class ProxyRuntime:
    """Per-proxy scraping state shared across the fetch pool.

    Rate windows and retry tracking are keyed by proxy: N fetchers on
    one proxy would otherwise silently allow N x the rate limit. All
    lookups are get-or-create without awaits, so they are race-free
    under asyncio. RetryTracker is int-keyed (it is shared with
    runemetrics), so each proxy gets a stable synthetic id.
    """

    def __init__(self, proxy_manager: ProxyManager) -> None:
        self.proxy_manager = proxy_manager
        proxy_settings = ProxySettings()  # type: ignore[call-arg]
        self._windows = [
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
        ]
        self._limiters: dict[str, RateLimiter] = {}
        self._apis: dict[str, HiscoreOldSchoolAPI] = {}
        self._trackers: dict[str, RetryTracker] = {}
        self._tracker_ids: dict[str, int] = {}
        self._next_tracker_id = 0

    def limiter(self, proxy: str) -> RateLimiter:
        """The proxy's shared rate limiter."""
        limiter = self._limiters.get(proxy)
        if limiter is None:
            limiter = RateLimiter(
                windows=list(self._windows), on_wait=on_rate_limit_wait
            )
            self._limiters[proxy] = limiter
        return limiter

    def api(self, proxy: str) -> HiscoreOldSchoolAPI:
        """The API client bound to the proxy's shared rate limiter."""
        api = self._apis.get(proxy)
        if api is None:
            api = HiscoreOldSchoolAPI(rate_limiter=self.limiter(proxy))
            self._apis[proxy] = api
        return api

    def tracker(self, proxy: str) -> tuple[RetryTracker, int]:
        """The proxy's retry tracker and its stable int id."""
        tracker = self._trackers.get(proxy)
        if tracker is None:
            tracker = RetryTracker(base_delay=1.0, max_delay=300.0, decay_window=300.0)
            self._trackers[proxy] = tracker
            self._tracker_ids[proxy] = self._next_tracker_id
            self._next_tracker_id += 1
        return tracker, self._tracker_ids[proxy]


async def get_proxy_list(proxy_manager: ProxyManager) -> list[str] | None:
    """The current proxy list, or None when the manager errors out."""
    proxies, error = await proxy_manager.get_proxy(None)
    if isinstance(proxies, list) and not error:
        return proxies
    logger.error(f"Error getting proxies: {error}")
    return None


def record_failure(runtime: ProxyRuntime, proxy: str) -> float:
    """Records a failed attempt and returns the proxy's backoff delay.

    Metrics + tracker update only; the caller owns the sleep so the
    backoff paces its own fetch slot.
    """
    _proxy = proxy_label(proxy)
    tracker, tracker_id = runtime.tracker(proxy)
    tracker.record_attempt(tracker_id, success=False)
    delay = tracker.get_backoff_delay(tracker_id)
    retry_count = tracker.get_retry_count(tracker_id)

    retry_counter.labels(proxy=_proxy).inc()
    retry_histogram.labels(proxy=_proxy).observe(retry_count)
    retry_delay_histogram.labels(proxy=_proxy).observe(delay)
    logger.warning(f"[{_proxy}]: backing off {delay:.2f}s")
    return delay


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
