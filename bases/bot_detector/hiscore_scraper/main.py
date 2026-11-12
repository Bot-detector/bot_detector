import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

from bot_detector.event_queue.adapters.kafka import (
    KafkaConfig,
    KafkaConsumerConfig,
    KafkaProducerConfig,
    KafkaSettings,
)
from bot_detector.event_queue.core import Queue, QueueProducer
from bot_detector.event_queue.factory import QueueFactory
from bot_detector.event_queue.structs import (
    NotFoundStruct,
    ScrapedStruct,
    ToScrapeStruct,
)
from bot_detector.hiscore_scraper.consumer import consume
from bot_detector.hiscore_scraper.fetcher import ProxyRuntime, fetch
from bot_detector.hiscore_scraper.metrics import start_metrics_server
from bot_detector.hiscore_scraper.processor import process
from bot_detector.hiscore_scraper.session import build_session
from bot_detector.hiscore_scraper.settings import Settings
from bot_detector.hiscore_scraper.structs import FetchResult
from bot_detector.proxy_manager import ProxyManager
from bot_detector.proxy_manager import Settings as ProxySettings

logger = logging.getLogger(__name__)


async def main():
    settings = Settings()
    start_metrics_server(port=settings.METRICS_PORT)
    proxy_manager = ProxyManager(api_key=ProxySettings().PROXY_API_KEY)  # type: ignore
    proxies = await proxy_manager.fetch_proxies()

    b_server = KafkaSettings().bootstrap_servers
    player_ts_queue = QueueFactory.create_queue(
        model=ToScrapeStruct,
        queue_type="queue",
        backend_type="kafka",
        config=KafkaConfig(
            topic="players.to_scrape",
            bootstrap_servers=b_server,
            producer=True,
            consumer=True,
            # slim payloads: always-null PlayerStruct optionals cost
            # ~1/3 of each message; consumers rehydrate them as None
            producer_config=KafkaProducerConfig(
                partition_key_fn=None,
                exclude_none=True,
            ),
            consumer_config=KafkaConsumerConfig(group_id="scraper"),
        ),
    )
    player_nf_producer = QueueFactory.create_queue(
        model=NotFoundStruct,
        queue_type="producer",
        backend_type="kafka",
        config=KafkaConfig(
            topic="players.not_found",
            bootstrap_servers=b_server,
            producer=True,
            producer_config=KafkaProducerConfig(partition_key_fn=None),
        ),
    )
    player_sc_producer = QueueFactory.create_queue(
        model=ScrapedStruct,
        queue_type="producer",
        backend_type="kafka",
        config=KafkaConfig(
            topic="players.scraped",
            bootstrap_servers=b_server,
            producer=True,
            producer_config=KafkaProducerConfig(
                partition_key_fn=lambda message: str(message.player_data.id % 10)
            ),
        ),
    )
    for queue in (player_ts_queue, player_nf_producer, player_sc_producer):
        if isinstance(queue, Exception):
            raise queue

    assert isinstance(player_ts_queue, Queue)
    assert isinstance(player_nf_producer, QueueProducer)
    assert isinstance(player_sc_producer, QueueProducer)

    await player_ts_queue.start()
    await player_nf_producer.start()
    await player_sc_producer.start()

    # in-process pipeline: kafka -> consume -> task_queue -> fetch pool
    # -> results_queue -> processors -> kafka. The bounded queues carry
    # backpressure: a slow stage stalls its producer (consumer lag grows,
    # the upstream producer throttles) instead of growing memory.
    runtime = ProxyRuntime(proxy_manager)
    task_queue: asyncio.Queue[ToScrapeStruct] = asyncio.Queue(
        maxsize=settings.TASK_QUEUE_MAXSIZE
    )
    results_queue: asyncio.Queue[FetchResult] = asyncio.Queue(
        maxsize=settings.RESULTS_QUEUE_MAXSIZE
    )

    stages: list[Coroutine[Any, Any, None]] = [
        consume(
            player_ts_queue=player_ts_queue,
            task_queue=task_queue,
            batch_size=settings.CONSUME_BATCH_SIZE,
        )
    ]
    session = build_session(connector_limit=settings.CONNECTION_LIMIT)
    stages += [
        fetch(
            fetcher_id=fetcher_id,
            runtime=runtime,
            task_queue=task_queue,
            results_queue=results_queue,
            session=session,
        )
        for fetcher_id in range(settings.FETCH_CONCURRENCY)
    ]
    stages += [
        process(
            processor_id=processor_id,
            results_queue=results_queue,
            player_ts_queue=player_ts_queue,
            player_nf_producer=player_nf_producer,
            player_sc_producer=player_sc_producer,
        )
        for processor_id in range(settings.PROCESS_CONCURRENCY)
    ]

    logger.info(
        f"Starting pipeline: 1 consumer, {settings.FETCH_CONCURRENCY} fetchers, "
        f"{settings.PROCESS_CONCURRENCY} processors, {len(proxies)} proxies."
    )

    try:
        await asyncio.gather(*stages)
    finally:
        await session.close()


async def run_async():
    await main()


def run():
    asyncio.run(run_async())


if __name__ == "__main__":
    run()
