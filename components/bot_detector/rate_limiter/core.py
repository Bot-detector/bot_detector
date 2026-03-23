import asyncio
import logging
import time
from collections import deque

logger = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self, calls_per_interval: int = 60, interval: int = 60) -> None:
        self.history = deque(maxlen=calls_per_interval)
        self.interval = interval

    async def check(self):
        """
        Checks if the rate limit is reached and waits if necessary.
        """
        current_time = int(time.time())
        self.history.append(current_time)

        # If history is full, calculate the time difference
        if len(self.history) == self.history.maxlen:
            first_call = self.history[0]
            time_span = current_time - first_call

            # If time_span is less than interval seconds, sleep for the remaining time
            if time_span < self.interval:
                sleep_time = self.interval - time_span
                logger.info(f"Rate limit reached. Sleeping for {sleep_time} seconds.")
                await asyncio.sleep(sleep_time)
