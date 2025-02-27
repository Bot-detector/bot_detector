import asyncio
import logging
from asyncio import Queue
from datetime import datetime

from aiohttp import ClientSession
from bot_detector.kafka_client import KafkaConsumer, KafkaProducer
from bot_detector.proxy_manager import ProxyManager
from bot_detector.runemetrics_api import RuneMetrics
from bot_detector.runemetrics_api.exceptions import UnexpectedRedirection
from bot_detector.schema import MetaData, Player, ScraperData
from osrs.utils import RateLimiter
from pydantic import ValidationError
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
        self.scraped_queue = scraped_queue
        self.not_found_queue = not_found_queue
        self.error_queue = error_queue

    async def run(self):
        """Main worker loop that continuously performs tasks using a proxy."""
        async with ClientSession() as session:
            while True:
                proxy, error = await self.proxy_manager.get_proxy(self.worker_id)
                proxy: str  # http://username:password@ip:port
                safe_proxy = f"http://{proxy.split('@')[1]}"
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
                    logger.info(f"Worker {self.worker_id}: Using proxy {safe_proxy}")
                    await self.perform_task(proxy=proxy, session=session)
                except Exception as e:
                    logger.error(
                        f"Worker {self.worker_id}: Error using proxy {safe_proxy}: {e}"
                    )
                    await asyncio.sleep(10)
                    continue

    async def perform_task(self, proxy: str, session: ClientSession):
        """Perform a specific task using the provided proxy."""
        logger.debug(f"Worker {self.worker_id}: Performing task with proxy {proxy}")

        # get name from kafka
        msg = await self.not_found_queue.get()
        player = Player(**msg[0].value)

        # get data from osrs hiscore
        try:
            api = RuneMetrics(proxy=proxy, rate_limiter=self.limiter)
            data = await api.get(
                player_name=player.name,
                session=session,
            )
        # push data to kafka players.not_found
        # await self.not_found_queue.put(item=player.model_dump(mode="json"))
        except UnexpectedRedirection:
            # push data to kafka: players.to_scrape
            await self.error_queue.put(item=player.model_dump(mode="json"))
            return
        except ValidationError as e:
            logger.error(f"Error validating player: {e} for {player.name}")
            await self.error_queue.put(item=player.model_dump(mode="json"))
            return

        player.updated_at = datetime.now()
        player.possible_ban = 1
        player.confirmed_player = 0

        match data.error:
            # username is not associated to an account
            case "NO_PROFILE":
                player.label_jagex = 1
            # account is perm banned
            case "NOT_A_MEMBER":
                player.label_jagex = 2
            # runemetrics is set to private. either they're too low level or they're banned.
            case "PROFILE_PRIVATE":
                player.label_jagex = 3
            case _:
                # account is active, probably just too low stats for hiscores
                player.label_jagex = 0

        hiscore_data = ScraperData(
            metadata=MetaData(version=1, source="runemetrics_scraper"),
            player_data=player,
            hiscore_data=None,
        )

        # push data players.scraped
        await self.scraped_queue.put(item=hiscore_data.model_dump(mode="json"))


async def main():
    global SETTINGS
    SETTINGS = Settings()
    proxy_manager = ProxyManager(api_key=SETTINGS.PROXY_API_KEY)
    proxies = await proxy_manager.fetch_proxies()

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
            topic="players.not_found",
            queue=not_found_queue,
            batch_size=1,
        ),
        await producer.produce(topic="players.not_found", queue=error_queue),
        await producer.produce(topic="players.scraped", queue=scraped_queue),
    ]

    workers = [
        Worker(
            worker_id=worker_id,
            proxy_manager=proxy_manager,
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
