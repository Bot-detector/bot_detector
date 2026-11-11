import asyncio
import logging
import time
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Window:
    """A rolling window capping the number of calls within an interval."""

    count: int
    interval_ms: int


DEFAULT_WINDOWS = (Window(count=60, interval_ms=60_000),)


class RateLimiter:
    def __init__(self, windows: Iterable[Window] | None = None) -> None:
        """
        Rolling-window rate limiter with millisecond resolution.

        Args:
            windows: Rate windows. A call only proceeds once every window
                has a free slot. Defaults to 60 calls per 60 seconds.

        Example:
            RateLimiter(
                windows=[
                    Window(count=1200, interval_ms=60_000),
                    Window(count=20, interval_ms=1_000),
                ]
            )
        """
        self.windows = tuple(windows) if windows is not None else DEFAULT_WINDOWS
        self._history: dict[Window, deque[int]] = {
            window: deque(maxlen=window.count) for window in self.windows
        }

    async def check(self):
        """
        Checks if any rate limit is reached and waits if necessary.
        """
        current_ms = int(time.time() * 1000)
        sleep_ms = 0
        for window, history in self._history.items():
            history.append(current_ms)
            if len(history) < window.count:
                continue
            time_span = current_ms - history[0]
            if time_span < window.interval_ms:
                sleep_ms = max(sleep_ms, window.interval_ms - time_span)
        if sleep_ms > 0:
            sleep_s = sleep_ms / 1000
            logger.info(f"Rate limit reached. Sleeping for {sleep_s:.3f} seconds.")
            await asyncio.sleep(sleep_s)
