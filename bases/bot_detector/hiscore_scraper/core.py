import asyncio
import logging

from aiohttp import ClientSession
from bot_detector.proxy_manager import ProxyManager
from osrs.asyncio import Hiscore, HSMode
from osrs.exceptions import PlayerDoesNotExist, UnexpectedRedirection
from osrs.utils import RateLimiter
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    PROXY_API_KEY: str


class Worker:
    def __init__(self, worker_id: int, proxy_manager: ProxyManager):
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
        player_name = "extreme4all"

        # get data from osrs hiscore
        try:
            hiscore_instance = Hiscore(proxy=proxy, rate_limiter=self.limiter)
            player_stats = await hiscore_instance.get(
                mode=HSMode.OLDSCHOOL,
                player=player_name,
                session=session,
            )
        except PlayerDoesNotExist:
            # TODO: push data to kafka runemetrics topic
            pass
        except UnexpectedRedirection:
            # TODO: push data to kafka scraper topic
            pass

        print(player_stats)
        # TODO: push data to kafka hiscore topic


async def main():
    SETTINGS = Settings()
    proxy_manager = ProxyManager(api_key=SETTINGS.PROXY_API_KEY)
    proxies = await proxy_manager.fetch_proxies()

    workers = [
        Worker(worker_id=i, proxy_manager=proxy_manager) for i in range(len(proxies))
    ]
    logger.info(f"Starting {len(workers)} workers.")

    await asyncio.gather(*[w.run() for w in workers])


if __name__ == "__main__":
    asyncio.run(main())
