import asyncio
import logging

from bot_detector.event_queue.core import Queue, QueueProducer
from bot_detector.event_queue.structs import (
    ScrapedStruct,
    ToScrapeStruct,
)
from bot_detector.structs import MetaData, PlayerStruct

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
    else:
        return Exception(
            f"Failed to produce player to scrape after {MAX_RETRIES} attempts: {error}"
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
    else:
        return Exception(
            f"Failed to produce scraped data after {MAX_RETRIES} attempts: {error}"
        )
