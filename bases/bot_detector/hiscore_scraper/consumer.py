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
    """Batches Kafka reads into the in-process task queue.

    Commit-on-dequeue: offsets are committed before the scrape happens,
    and at-least-once delivery comes from requeueing failures to
    players.to_scrape, not from offset rewinds. A failed batch commit
    just means those players may be redelivered. The bounded task_queue
    applies backpressure to the consumer (and upstream, via consumer
    lag) when the pool is slow.
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
