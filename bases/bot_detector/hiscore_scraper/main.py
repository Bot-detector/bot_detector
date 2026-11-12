import asyncio
import logging

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
from bot_detector.hiscore_scraper.metrics import start_metrics_server
from bot_detector.hiscore_scraper.settings import Settings
from bot_detector.hiscore_scraper.worker import work
from bot_detector.proxy_manager import ProxyManager
from bot_detector.proxy_manager import Settings as ProxySettings

logger = logging.getLogger(__name__)


async def main():
    start_metrics_server(port=Settings().METRICS_PORT)
    proxy_manager = ProxyManager(api_key=ProxySettings().PROXY_API_KEY)  # type: ignore
    proxies = await proxy_manager.fetch_proxies()

    # initialize kafka producers and consumers
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
    # start workers
    workers = [
        work(
            worker_id=worker_id,
            proxy_manager=proxy_manager,
            player_ts_queue=player_ts_queue,
            player_nf_producer=player_nf_producer,
            player_sc_producer=player_sc_producer,
        )
        for worker_id in range(len(proxies))
    ]
    logger.info(f"Starting {len(workers)} workers.")

    await asyncio.gather(*[w for w in workers])


async def run_async():
    await main()


def run():
    asyncio.run(run_async())


if __name__ == "__main__":
    run()
    # test if cicd runs
