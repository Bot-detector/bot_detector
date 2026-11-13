import asyncio
import logging

from bot_detector.event_queue.core import Queue, QueueProducer
from bot_detector.event_queue.structs import (
    NotFoundStruct,
    ScrapedStruct,
    ToScrapeStruct,
)
from bot_detector.hiscore_scraper.errors import dump_error
from bot_detector.hiscore_scraper.flow.structs import FetchResult
from bot_detector.hiscore_scraper.player_outcomes.metrics import not_found_counter
from bot_detector.hiscore_scraper.player_outcomes.service import (
    produce_not_found,
    produce_player_scraped,
    produce_player_to_scrape,
)
from bot_detector.hiscore_scraper.scraping.service import (
    proxy_label,
    transform_player_stats,
)
from bot_detector.osrs_hs_api.exceptions import PlayerDoesNotExist
from bot_detector.wide_event import WideEventLogger

logger = logging.getLogger(__name__)
wide_event = WideEventLogger()


def _force_log() -> None:
    wide_event.add({"force_log": True})


def _emit() -> None:
    """Emits one wide event per fetch result.

    Produce failures log at error, scrape failures at warning; the
    remaining outcomes log at info when forced or sampled.
    """
    ctx = wide_event.get()
    force_log = bool(ctx.pop("force_log", False))
    if "produce_errors" in ctx:
        logger.error(ctx)
    elif "scrape_error" in ctx:
        logger.warning(ctx)
    elif force_log:
        ctx.update({"log_reason": "force"})
        logger.info(ctx)
    elif wide_event.sample():
        ctx.update({"log_reason": "sample"})
        logger.info(ctx)


async def process(
    processor_id: int,
    results_queue: asyncio.Queue[FetchResult],
    player_ts_queue: Queue[ToScrapeStruct],
    player_nf_producer: QueueProducer[NotFoundStruct],
    player_sc_producer: QueueProducer[ScrapedStruct],
):
    """Turns fetch outcomes into Kafka side effects.

    Each result emits one wide event: player/proxy context, the
    outcome, and errors dumped to JSON (text fallback) when present.
    """
    while True:
        result = await results_queue.get()
        player_data = result.player
        token = wide_event.set({})
        try:
            wide_event.add(
                {
                    "processor": processor_id,
                    "player": {"id": player_data.id, "name": player_data.name},
                    "proxy": proxy_label(result.proxy),
                }
            )

            if result.error is not None:
                if isinstance(result.error, PlayerDoesNotExist):
                    not_found_counter.labels(proxy=result.proxy).inc()
                    player_data.possible_ban = True
                    wide_event.add({"outcome": "not_found"})
                    error = await produce_not_found(player_nf_producer, player_data)
                    if error:
                        wide_event.add(
                            {"produce_errors": {"not_found": dump_error(error)}}
                        )
                    continue

                wide_event.add(
                    {"outcome": "error", "scrape_error": dump_error(result.error)}
                )
                error = await produce_player_to_scrape(player_ts_queue, player_data)
                if error:
                    wide_event.add({"produce_errors": {"to_scrape": dump_error(error)}})
                continue

            assert result.stats is not None  # for mypy
            wide_event.add({"outcome": "success"})
            scraped_data = await transform_player_stats(
                player_stats=result.stats,
                player=player_data,
            )
            if scraped_data is None:
                # transform logged the validation error; the requeue
                # lives here so scraping never touches player outcomes
                wide_event.add({"outcome": "transform_failed"})
                _force_log()
                error = await produce_player_to_scrape(player_ts_queue, player_data)
                if error:
                    wide_event.add({"produce_errors": {"to_scrape": dump_error(error)}})
                continue

            error = await produce_player_scraped(player_sc_producer, scraped_data)
            if error:
                wide_event.add(
                    {
                        "outcome": "error",
                        "produce_errors": {"scraped": dump_error(error)},
                    }
                )
                requeue_error = await produce_player_to_scrape(
                    player_ts_queue, player_data
                )
                if requeue_error:
                    wide_event.add(
                        {"produce_errors": {"to_scrape": dump_error(requeue_error)}}
                    )
        finally:
            _emit()
            wide_event.reset(token)
