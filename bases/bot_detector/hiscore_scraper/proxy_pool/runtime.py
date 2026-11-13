from bot_detector.hiscore_scraper.proxy_pool.metrics import on_rate_limit_wait
from bot_detector.osrs_hs_api import HiscoreOldSchoolAPI
from bot_detector.proxy_manager import ProxyManager
from bot_detector.proxy_manager import Settings as ProxySettings
from bot_detector.rate_limiter import RateLimiter, Window
from bot_detector.retry_tracker import RetryTracker


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
