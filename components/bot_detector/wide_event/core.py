import random
from contextvars import ContextVar
from typing import Any

from .interface import EventLoggerInterface


class WideEventLogger(EventLoggerInterface):
    """
    Manages wide event logging context across an async application.
    """

    def __init__(self, sample_ratio: float = 0.1) -> None:
        self.ctx: ContextVar[dict[str, Any]] = ContextVar("context", default={})
        self.sample_ratio = sample_ratio

    def set(self, data: dict[str, Any] = {}) -> Any:
        """Set the current context to the provided data, returning a token for later reset."""
        return self.ctx.set(data)

    def reset(self, token: Any) -> None:
        """Reset the context to a previous state using the provided token."""
        self.ctx.reset(token)

    def get(self) -> dict[str, Any]:
        """Return a copy of the current context."""
        return self.ctx.get().copy()

    def add(self, data: dict[str, Any]) -> None:
        """Merge new data into the current context."""
        current = self.ctx.get()
        merged = self._merge(current, data)
        self.ctx.set(merged)

    def sample(self) -> bool:
        """Return True if the current event should be logged based on the sample ratio."""
        return random.random() < self.sample_ratio

    def _merge(self, a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
        """Recursively merge dictionary b into a."""
        if not isinstance(a, dict) or not isinstance(b, dict):
            raise TypeError("Both arguments must be dicts")

        for key, value in b.items():
            if key in a and isinstance(a[key], dict) and isinstance(value, dict):
                a[key] = self._merge(a[key], value)
            else:
                a[key] = value
        return a
