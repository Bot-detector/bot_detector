from bot_detector.hiscore_scraper.proxy_pool.metrics import on_rate_limit_wait
from bot_detector.hiscore_scraper.proxy_pool.runtime import ProxyRuntime
from bot_detector.hiscore_scraper.proxy_pool.service import (
    get_proxy_list,
    record_failure,
)

__all__ = [
    "ProxyRuntime",
    "get_proxy_list",
    "on_rate_limit_wait",
    "record_failure",
]
