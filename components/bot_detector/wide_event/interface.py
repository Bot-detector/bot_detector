from typing import Any, Protocol


class EventLoggerInterface(Protocol):  # pragma: no cover
    """
    Manages wide event logging context across an async application.
    """

    def __init__(self, sample_ratio: float) -> None: ...

    def set(self, data: dict[str, Any] = {}) -> Any:
        """Set the current context to the provided data, returning a token for later reset."""
        ...

    def reset(self, token: Any) -> None:
        """Reset the context to a previous state using the provided token."""
        ...

    def get(self) -> dict[str, Any]:
        """Return a copy of the current context."""
        ...

    def add(self, data: dict[str, Any]) -> None:
        """Merge new data into the current context."""
        ...

    def sample(self) -> bool:
        """Return True if the current event should be logged based on the sample ratio."""
        ...
