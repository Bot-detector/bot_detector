class EventQueueError(Exception):
    """Base exception for event queue errors."""


class MessageTypeError(EventQueueError):
    """Raised when a message payload has an unexpected type."""


class ProducerNotStartedError(EventQueueError):
    """Raised when a producer operation happens before start."""


class ProducerConfigError(EventQueueError):
    """Raised when producer configuration is missing or invalid."""


class ConsumerNotStartedError(EventQueueError):
    """Raised when a consumer operation happens before start."""


class ConsumerConfigError(EventQueueError):
    """Raised when consumer configuration is missing or invalid."""


class ConsumerFetchError(EventQueueError):
    """Raised when a consumer fails to fetch messages."""

    def __init__(self, message: str, *, cause: Exception) -> None:
        super().__init__(message)
        self.cause = cause
