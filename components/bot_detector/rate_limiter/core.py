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
        Reserves a call slot in every window, sleeping until it opens.

        A reservation is recorded for the time the call will actually
        fire, not for check-in time: a full window frees its next slot
        at oldest + interval. At most `count` reservations exist in any
        `interval` span, so concurrent callers cannot overshoot the
        limit, and they wake spaced out instead of in one herd.
        Uncontended calls reserve `now` and return without sleeping.

        The compute + append section has no await, so it is atomic under
        asyncio; no lock is needed.
        """
        now_ms = int(time.time() * 1000)
        scheduled_ms = now_ms
        blocked: list[Window] = []
        # window freeing the latest; it dictates the sleep duration
        binding: tuple[Window, int] | None = None
        for window, history in self._history.items():
            if len(history) < window.count:
                continue
            free_at = history[0] + window.interval_ms
            if free_at > scheduled_ms:
                scheduled_ms = free_at
                binding = (window, free_at)
            if free_at > now_ms:
                blocked.append(window)
        for history in self._history.values():
            history.append(scheduled_ms)
        wait_ms = scheduled_ms - now_ms
        if wait_ms <= 0:
            return

        wait_s = wait_ms / 1000
        if self.on_wait is not None:
            self.on_wait(
                WaitEvent(blocked=tuple(blocked), binding=binding[0], wait_s=wait_s)
            )
        logger.info(f"Rate limit reached. Waiting {wait_s:.3f} seconds for a slot.")
        await asyncio.sleep(wait_s)
