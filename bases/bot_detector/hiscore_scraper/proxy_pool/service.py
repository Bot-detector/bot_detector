import logging

from bot_detector.hiscore_scraper.proxy_pool.metrics import (
    retry_counter,
    retry_delay_histogram,
    retry_histogram,
)
from bot_detector.hiscore_scraper.proxy_pool.runtime import ProxyRuntime
from bot_detector.hiscore_scraper.scraping.service import proxy_label
from bot_detector.proxy_manager import ProxyManager

logger = logging.getLogger(__name__)


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
