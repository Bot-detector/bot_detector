import asyncio
import logging
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Window:
    """A named rolling window capping the number of calls within an interval."""

    name: str
    count: int
    interval_ms: int


@dataclass(frozen=True)
class WaitEvent:
    """Emitted when a check had to wait for a window to free up."""

    blocked: tuple[Window, ...]  # windows that were exhausted
    binding: Window  # window dictating the wait duration
    wait_s: float


class RateLimiter:
    def __init__(
        self,
        windows: list[Window],
        on_wait: Callable[[WaitEvent], None] | None = None,
    ) -> None:
        """
        Rolling-window rate limiter with millisecond resolution.

        Args:
            windows: Rate windows. A call only proceeds once every window
                has a free slot.
            on_wait: Observer for waits, e.g. to record metrics. Called
                synchronously before the sleep; keep it fast.

        Example:
            RateLimiter(
                windows=[
                    Window(name="minute", count=1200, interval_ms=60_000),
                    Window(name="second", count=20, interval_ms=1_000),
                ]
            )
        """
        self.windows = tuple(windows)
        self.on_wait = on_wait
        self._history: dict[Window, deque[int]] = {
            window: deque(maxlen=window.count) for window in self.windows
        }

    async def check(self):
        """
        Checks if any rate limit is reached and waits if necessary.
        """
        current_ms = int(time.time() * 1000)
        blocked: list[Window] = []
        # window with the longest wait; it dictates the sleep duration
        binding: tuple[Window, int] | None = None
        for window, history in self._history.items():
            history.append(current_ms)
            if len(history) < window.count:
                continue
            time_span = current_ms - history[0]
            if time_span < window.interval_ms:
                blocked.append(window)
                wait_ms = window.interval_ms - time_span
                if binding is None or wait_ms > binding[1]:
                    binding = (window, wait_ms)
        if binding is None:
            return

        wait_s = binding[1] / 1000
        if self.on_wait is not None:
            self.on_wait(
                WaitEvent(blocked=tuple(blocked), binding=binding[0], wait_s=wait_s)
            )
        logger.info(f"Rate limit reached. Sleeping for {wait_s:.3f} seconds.")
        await asyncio.sleep(wait_s)
