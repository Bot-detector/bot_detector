import asyncio
import json
import logging
from asyncio import Queue

from aiohttp import ClientSession
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from AioKafkaEngine import ConsumerEngine, ProducerEngine
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

    async def perform_task(self, proxy: str, session: ClientSession):
        """Perform a specific task using the provided proxy."""
        logger.debug(f"Worker {self.worker_id}: Performing task with proxy {proxy}")

        # TODO: get name from kafka
        player: Player = await self.to_scrape_queue.get()
        print(player)
        # player = {}
        # player_name = "extreme4all"

        # get data from osrs hiscore
        try:
            hiscore_instance = Hiscore(proxy=proxy, rate_limiter=self.limiter)
            player_stats = await hiscore_instance.get(
                mode=HSMode.OLDSCHOOL,
                player=player.name,
                session=session,
            )
        except PlayerDoesNotExist:
            # TODO: push data to kafka runemetrics topic
            await self.not_found_queue.put(item=player)
            pass
        except UnexpectedRedirection:
            # TODO: push data to kafka scraper topic
            self.error_queue.put(item=player)
            pass

        hiscore_data = {
            "skills": {
                skill.name: skill.xp for skill in player_stats.skills if skill.xp > 0
            },
            "activities": {
                activity.name: activity.score
                for activity in player_stats.activities
                if activity.score > 0
            },
        }
        print(hiscore_data)

        # TODO: push data to kafka hiscore topic
        await self.scraped_queue.put(item=hiscore_data)


async def consume_players_to_scrape(queue: Queue):
    engine = ConsumerEngine(
        consumer=AIOKafkaConsumer(
            *["players.to_scrape"],
            bootstrap_servers=SETTINGS.KAFKA_BOOTSTRAP_SERVERS,
            group_id="my_group",
            value_deserializer=lambda x: json.loads(x.decode("utf-8")),
            auto_offset_reset="earliest",
        ),
        queue=queue,
        batch_size=10,
        timeout=1,
    )
    await engine.start()
    return asyncio.create_task(engine.consume())


async def produce_players_to_scrape(queue: Queue):
    engine = ProducerEngine(
        producer=AIOKafkaProducer(
            bootstrap_servers=SETTINGS.KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode(),
            acks="all",
        ),
        queue=queue,
        topic="players.to_scrape",
    )
    await engine.start()

    return asyncio.create_task(engine.produce())


async def produce_scraped_players(queue: Queue):
    engine = ProducerEngine(
        producer=AIOKafkaProducer(
            bootstrap_servers=SETTINGS.KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode(),
            acks="all",
        ),
        queue=queue,
        topic="players.scraped",
    )
    await engine.start()

    return asyncio.create_task(engine.produce())


async def produce_players_not_found(queue: Queue):
    engine = ProducerEngine(
        producer=AIOKafkaProducer(
            bootstrap_servers=SETTINGS.KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode(),
            acks="all",
        ),
        queue=queue,
        topic="players.not_found",
    )
    await engine.start()

    return asyncio.create_task(engine.produce())


async def main():
    global SETTINGS
    SETTINGS = Settings()
    proxy_manager = ProxyManager(api_key=SETTINGS.PROXY_API_KEY)
    proxies = await proxy_manager.fetch_proxies()

    to_scrape_queue = Queue()
    error_queue = Queue()
    scraped_queue = Queue()
    not_found_queue = Queue()

    kafka_tasks = [
        await consume_players_to_scrape(queue=to_scrape_queue),
        await produce_players_to_scrape(queue=error_queue),
        await produce_scraped_players(queue=scraped_queue),
        await produce_players_not_found(queue=not_found_queue),
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


if __name__ == "__main__":
    asyncio.run(main())
