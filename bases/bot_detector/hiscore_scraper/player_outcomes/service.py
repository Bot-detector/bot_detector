import asyncio
import logging
from collections.abc import Callable
from typing import TypeVar

from bot_detector.event_queue.core import Queue, QueueProducer
from bot_detector.event_queue.structs import (
    NotFoundStruct,
    ScrapedStruct,
    ToScrapeStruct,
)
from bot_detector.structs import MetaData, PlayerStruct
from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

MAX_RETRIES = 3


async def produce_with_retry(
    producer: QueueProducer[T],
    build: Callable[[], T],
    label: str,
    max_retries: int = MAX_RETRIES,
) -> Exception | None:
    """Produces a message with exponential-backoff retries.

    Returns None on success, or the last error after exhausting
    attempts. The caller decides how to surface the failure.
    """
    error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        error = await producer.put([build()])
        if error is None:
            return None
        logger.error(f"Failed to {label} (attempt {attempt}): {error}")
        await asyncio.sleep(2**attempt)  # Exponential backoff
    return Exception(f"Failed to {label} after {max_retries} attempts: {error}")


async def produce_player_to_scrape(
    player_ts_queue: Queue[ToScrapeStruct],
    player: PlayerStruct,
) -> Exception | None:
    return await produce_with_retry(
        player_ts_queue,
        lambda: ToScrapeStruct(
            metadata=MetaData(version=1, source="hiscore_scraper"),
            player_data=player,
        ),
        label="produce player to scrape",
    )


async def produce_not_found(
    player_nf_producer: QueueProducer[NotFoundStruct],
    player: PlayerStruct,
) -> Exception | None:
    return await produce_with_retry(
        player_nf_producer,
        lambda: NotFoundStruct(
            metadata=MetaData(version=1, source="hiscore_scraper"),
            player_data=player,
        ),
        label="produce not found",
    )


async def produce_player_scraped(
    player_sc_producer: QueueProducer[ScrapedStruct],
    scraped_data: ScrapedStruct,
) -> Exception | None:
    return await produce_with_retry(
        player_sc_producer,
        lambda: scraped_data,
        label="produce scraped data",
    )
