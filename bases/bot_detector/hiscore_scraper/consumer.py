import asyncio
import logging

from bot_detector.event_queue.core import Queue
from bot_detector.event_queue.structs import ToScrapeStruct

logger = logging.getLogger(__name__)


async def consume(
    player_ts_queue: Queue[ToScrapeStruct],
    task_queue: asyncio.Queue[ToScrapeStruct],
    batch_size: int,
):
    """Consume stage: batches Kafka reads, hands players to the pool.

    Replaces the old per-player get_one + commit: one get_many per batch
    and one commit per batch, so the shared consumer's commit round trip
    no longer sits on every scrape's critical path (it used to cap the
    whole fleet at 1/commit_rtt).

    Commit-on-dequeue matches the old semantics exactly: offsets are
    committed before the scrape happens, and at-least-once delivery is
    provided by requeueing failures to players.to_scrape, not by offset
    rewinds. A failed batch commit just means those players may be
    redelivered later; a bounded task_queue applies backpressure to the
    consumer (and upstream, via consumer lag) when the pool is slow.
    """
    while True:
        batch = await player_ts_queue.get_many(batch_size)
        if isinstance(batch, Exception):
            logger.error(f"Error consuming player batch: {batch}")
            await asyncio.sleep(1)
            continue
        if not batch:
            continue

        for player_to_scrape in batch:
            await task_queue.put(player_to_scrape)

        commit_error = await player_ts_queue.commit()
        if commit_error:
            logger.error(f"Error committing player batch offset: {commit_error}")
