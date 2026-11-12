import asyncio
import logging

from bot_detector.event_queue.core import Queue, QueueProducer
from bot_detector.event_queue.structs import (
    NotFoundStruct,
    ScrapedStruct,
    ToScrapeStruct,
)
from bot_detector.hiscore_scraper.metrics import not_found_counter
from bot_detector.hiscore_scraper.producers import (
    produce_not_found,
    produce_player_scraped,
    produce_player_to_scrape,
)
from bot_detector.hiscore_scraper.scrape import transform_player_stats
from bot_detector.hiscore_scraper.structs import FetchResult
from bot_detector.osrs_hs_api.exceptions import PlayerDoesNotExist

logger = logging.getLogger(__name__)


async def process(
    processor_id: int,
    results_queue: asyncio.Queue[FetchResult],
    player_ts_queue: Queue[ToScrapeStruct],
    player_nf_producer: QueueProducer[NotFoundStruct],
    player_sc_producer: QueueProducer[ScrapedStruct],
):
    """Turns fetch outcomes into Kafka side effects.

    CPU + Kafka only (transform, produce): never stalls on Jagex. The
    fetch pool owns outcome branching, this stage owns durability:
    every failure path ends in a Kafka requeue, so delivery is
    at-least-once.
    """
    while True:
        result = await results_queue.get()
        player_data = result.player
        log_prefix = f"[processor-{processor_id}][{player_data.name}]"

        if result.error is not None:
            if isinstance(result.error, PlayerDoesNotExist):
                not_found_counter.labels(proxy=result.proxy).inc()
                player_data.possible_ban = True
                error = await produce_not_found(player_nf_producer, player_data)
                if error:
                    logger.error(f"{log_prefix}: {error}")
                continue

            logger.warning(f"{log_prefix}: {result.error=}")
            error = await produce_player_to_scrape(player_ts_queue, player_data)
            if error:
                logger.error(f"{log_prefix}: {error}")
            continue

        assert result.stats is not None  # for mypy
        scraped_data = await transform_player_stats(
            player_stats=result.stats,
            player=player_data,
            player_ts_producer=player_ts_queue,
        )
        if scraped_data is None:
            # transform already requeued the player to players.to_scrape;
            # a backoff sleep here would stall every fetch result, so the
            # Kafka round trip is the retry pacing
            continue

        error = await produce_player_scraped(player_sc_producer, scraped_data)
        if error:
            logger.error(f"{log_prefix}: {error}")
            requeue_error = await produce_player_to_scrape(player_ts_queue, player_data)
            if requeue_error:
                logger.error(f"{log_prefix}: {requeue_error}")
