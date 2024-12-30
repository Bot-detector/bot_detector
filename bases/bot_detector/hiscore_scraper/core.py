import asyncio
import logging
from asyncio import Queue

from aiohttp import ClientSession
from bot_detector.kafka_client import KafkaConsumer, KafkaProducer
from bot_detector.proxy_manager import ProxyManager
from bot_detector.schema import Player
from osrs.asyncio import Hiscore, HSMode
from osrs.exceptions import PlayerDoesNotExist, UnexpectedRedirection
from osrs.utils import RateLimiter
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    PROXY_API_KEY: str
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9094"


class Worker:
    def __init__(
        self,
        worker_id: int,
        proxy_manager: ProxyManager,
        to_scrape_queue: Queue,
        scraped_queue: Queue,
        not_found_queue: Queue,
        error_queue: Queue,
    ):
        """
        Initialize the worker.

        Args:
            worker_id (int): Unique identifier for the worker.
            proxy_manager (ProxyManager): Instance of ProxyManager to retrieve proxies.
        """
        self.worker_id = worker_id
        self.proxy_manager = proxy_manager
        # 100 calls per minute
        self.limiter = RateLimiter(calls_per_interval=100, interval=60)
        # queue's
        self.to_scrape_queue = to_scrape_queue
        self.scraped_queue = scraped_queue
        self.not_found_queue = not_found_queue
        self.error_queue = error_queue

    async def run(self):
        """Main worker loop that continuously performs tasks using a proxy."""
        async with ClientSession() as session:
            while True:
                proxy, error = await self.proxy_manager.get_proxy(self.worker_id)

                # lets have this send us a bunch of errors so we certainly don't miss it
                if error:
                    logger.error(f"Worker {self.worker_id}: {error}")
                    await asyncio.sleep(10)
                    continue

                if proxy is None:
                    logger.error(f"Worker {self.worker_id}: No proxy available.")
                    await asyncio.sleep(10)
                    continue

                try:
                    logger.info(f"Worker {self.worker_id}: Using proxy {proxy}")
                    await self.perform_task(proxy=proxy, session=session)
                except Exception as e:
                    logger.error(
                        f"Worker {self.worker_id}: Error using proxy {proxy}: {e}"
                    )
                    await asyncio.sleep(10)
                    continue

    async def perform_task(self, proxy: str, session: ClientSession):
        """Perform a specific task using the provided proxy."""
        logger.debug(f"Worker {self.worker_id}: Performing task with proxy {proxy}")

        # get name from kafka
        msg = await self.to_scrape_queue.get()
        player = Player(**msg[0].value)

        # get data from osrs hiscore
        try:
            hiscore_instance = Hiscore(proxy=proxy, rate_limiter=self.limiter)
            player_stats = await hiscore_instance.get(
                mode=HSMode.OLDSCHOOL,
                player=player.name,
                session=session,
            )
        except PlayerDoesNotExist:
            # push data to kafka players.not_found
            await self.not_found_queue.put(item=player.model_dump(mode="json"))
            return
        except UnexpectedRedirection:
            # push data to kafka: players.to_scrape
            self.error_queue.put(item=player.model_dump(mode="json"))
            return

        hiscore_data = {
            "player_data": player.model_dump(),
            "hiscore_data": {
                "skills": {
                    skill.name: skill.xp
                    for skill in player_stats.skills
                    if skill.xp > 0
                },
                "activities": {
                    activity.name: activity.score
                    for activity in player_stats.activities
                    if activity.score > 0
                },
            },
        }
        print(hiscore_data)

        # push data players.scraped
        await self.scraped_queue.put(item=hiscore_data)


async def main():
    global SETTINGS
    SETTINGS = Settings()
    proxy_manager = ProxyManager(api_key=SETTINGS.PROXY_API_KEY)
    proxies = await proxy_manager.fetch_proxies()

    to_scrape_queue = Queue()
    error_queue = Queue()
    scraped_queue = Queue()
    not_found_queue = Queue()

    # Kafka Consumers
    consumer = KafkaConsumer(
        bootstrap_servers=SETTINGS.KAFKA_BOOTSTRAP_SERVERS,
        group_id="scraper",
    )

    # Kafka Producers
    producer = KafkaProducer(bootstrap_servers=SETTINGS.KAFKA_BOOTSTRAP_SERVERS)

    kafka_tasks = [
        await consumer.consume(
            topic="players.to_scrape",
            queue=to_scrape_queue,
            batch_size=1,
        ),
        await producer.produce(topic="players.to_scrape", queue=error_queue),
        await producer.produce(topic="players.scraped", queue=scraped_queue),
        await producer.produce(topic="players.not_found", queue=not_found_queue),
    ]

    workers = [
        Worker(
            worker_id=worker_id,
            proxy_manager=proxy_manager,
            to_scrape_queue=to_scrape_queue,
            scraped_queue=scraped_queue,
            not_found_queue=not_found_queue,
            error_queue=error_queue,
        )
        for worker_id in range(len(proxies))
    ]
    logger.info(f"Starting {len(workers)} workers.")

    await asyncio.gather(*[w.run() for w in workers], *kafka_tasks)


def run():
    asyncio.run(main())


if __name__ == "__main__":
    run()
