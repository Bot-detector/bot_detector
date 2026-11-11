import asyncio
import logging
import time
from collections import deque

logger = logging.getLogger(__name__)


class _Window:
    """A single rolling window capping the number of recorded calls."""

    def __init__(self, calls_per_interval: int, interval: int) -> None:
        self.calls_per_interval = calls_per_interval
        self.interval = interval
        self.history: deque[int] = deque(maxlen=calls_per_interval)

    def record(self, current_time: int) -> None:
        self.history.append(current_time)

    def sleep_time(self, current_time: int) -> int:
        """Seconds until a free slot opens, zero if the window has capacity."""
        if len(self.history) < self.calls_per_interval:
            return 0
        first_call = self.history[0]
        time_span = current_time - first_call
        if time_span < self.interval:
            return self.interval - time_span
        return 0


class RateLimiter:
    def __init__(
        self,
        calls_per_interval: int = 60,
        interval: int = 60,
        extra_windows: list[tuple[int, int]] | None = None,
    ) -> None:
        """
        Rolling-window rate limiter.

        Args:
            calls_per_interval: Max calls allowed within `interval` seconds.
            interval: Length of the primary window in seconds.
            extra_windows: Additional (calls_per_interval, interval) windows.
                A call only proceeds once every window has a free slot.
        """
        windows = [(calls_per_interval, interval)]
        if extra_windows:
            windows.extend(extra_windows)
        self.windows = [_Window(calls, seconds) for calls, seconds in windows]

        # primary window, exposed for backwards compatibility
        self.history = self.windows[0].history
        self.interval = interval

    async def check(self):
        """
        Checks if any rate limit is reached and waits if necessary.
        """
        current_time = int(time.time())
        for window in self.windows:
            window.record(current_time)

        sleep_time = max(window.sleep_time(current_time) for window in self.windows)
        if sleep_time > 0:
            logger.info(f"Rate limit reached. Sleeping for {sleep_time} seconds.")
            await asyncio.sleep(sleep_time)
