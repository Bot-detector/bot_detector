import random
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class RetryState:
    consecutive_failures: int = 0
    last_attempt: float = 0.0
    last_success: Optional[float] = None


class RetryTracker:
    """
    Tracks retry attempts per worker with adaptive exponential backoff.

    Features:
    - Exponential backoff: base_delay * 2^consecutive_failures
    - Jitter: Randomizes delay to prevent thundering herd
    - Time decay: Reduces retry count if no failures in recent window
    - Success reset: Resets consecutive failures on successful operation
    """

    def __init__(
        self,
        base_delay: float = 10.0,
        max_delay: float = 300.0,
        decay_window: float = 300.0,
        jitter_factor: float = 0.5,
    ):
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.decay_window = decay_window
        self.jitter_factor = jitter_factor
        self._states: dict[int, RetryState] = {}

    def get_backoff_delay(self, worker_id: int) -> float:
        state = self._states.get(worker_id, RetryState())
        now = time.time()

        if now - state.last_attempt > self.decay_window:
            state.consecutive_failures = 0

        exponential_delay = self.base_delay * (2**state.consecutive_failures)
        capped_delay = min(exponential_delay, self.max_delay)

        jittered_delay = capped_delay * random.uniform(
            1 - self.jitter_factor,
            1 + self.jitter_factor,
        )

        return min(max(jittered_delay, 1.0), self.max_delay)

    def record_attempt(self, worker_id: int, success: bool = False):
        if worker_id not in self._states:
            self._states[worker_id] = RetryState()

        state = self._states[worker_id]
        now = time.time()
        state.last_attempt = now

        if success:
            state.consecutive_failures = 0
            state.last_success = now
        else:
            state.consecutive_failures += 1

    def get_retry_count(self, worker_id: int) -> int:
        state = self._states.get(worker_id, RetryState())
        now = time.time()

        if now - state.last_attempt > self.decay_window:
            return 0
        return state.consecutive_failures
