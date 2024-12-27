import asyncio
import logging

from bot_detector.proxy_manager import ProxyManager

logger = logging.getLogger(__name__)


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

    async def run(self):
        """Main worker loop that continuously performs tasks using a proxy."""
        while True:
            proxy = await self.proxy_manager.get_proxy(self.worker_id)
            if not proxy:
                logger.debug(
                    f"Worker {self.worker_id}: No proxy available. Retrying..."
                )
                await asyncio.sleep(5)
                continue
            try:
                logger.info(f"Worker {self.worker_id}: Using proxy {proxy}")
                await self.perform_task(proxy)
            except Exception as e:
                logger.error(f"Worker {self.worker_id}: Error using proxy {proxy}: {e}")

    async def perform_task(self, proxy):
        """Perform a specific task using the provided proxy."""
        # Replace this with your actual asynchronous task logic
        logger.debug(f"Worker {self.worker_id}: Performing task with proxy {proxy}")
        await asyncio.sleep(1)  # Simulate task execution
