import logging

from prometheus_client import Counter

logger = logging.getLogger(__name__)


not_found_counter = Counter(
    name="hiscore_scraper_not_found",
    documentation="Count of players not found",
    labelnames=["proxy"],
)
