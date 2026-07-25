import asyncio
import logging
from typing import (
    Generic,
    TypeVar,
)

from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class Batcher(Generic[T]):
    """
    Collect events until batch_size or timeout is reached.
    Each _consume_many call gets its own Batcher instance.
    """

    def __init__(self, batch_size: int, timeout_ms: int):
        self.batch_size = batch_size
        self.timeout_ms = timeout_ms
        self._buffer: list[T] = []
        self._start_time = asyncio.get_running_loop().time()

    @property
    def size(self) -> int:
        """Current size of the buffer."""
        return len(self._buffer)

    @property
    def time_left(self) -> float:
        """Time left before timeout in seconds."""
        elapsed_sec = asyncio.get_running_loop().time() - self._start_time
        return max(0.0, self.timeout_ms / 1000 - elapsed_sec)

    def append(self, event: T, auto: bool = True) -> list[T] | None:
        """Append event to buffer and flush if needed."""
        self._buffer.append(event)
        if auto and self.check_flush():
            return self.flush()
        return None

    def check_flush(self) -> bool:
        """Check if batch should be flushed based on size or timeout."""
        if len(self._buffer) >= self.batch_size:
            return True
        current_time = asyncio.get_running_loop().time()
        if (current_time - self._start_time) >= self.timeout_ms / 1000:
            return True
        return False

    def flush(self) -> list[T]:
        if not self._buffer:
            return []
        batch = self._buffer
        self._buffer = []
        self._start_time = asyncio.get_running_loop().time()  # reset timer
        return batch
