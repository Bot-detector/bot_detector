from unittest.mock import AsyncMock

from pydantic import BaseModel


# --- Message model ---
class TestMessage(BaseModel):
    id: str
    data: str


# --- Dummy consumer & producer ---
class DummyConsumer:
    """
    Simulates a Kafka consumer. Uses a list of dicts to simulate messages and errors.
    Each item in `queue` is either:
        {"message": TestMessage(...)}  -> a normal message
        {"error": "some error"}        -> a consumer error
    """

    def __init__(self, queue: list[dict] | None = None) -> None:
        self.queue = queue or []
        self.start = AsyncMock()
        self.stop = AsyncMock()
        self.commit = AsyncMock()
        self.get_consumer = AsyncMock()

    async def consume_one(self) -> tuple[TestMessage | None, str | None]:
        if not self.queue:
            return None, None
        item = self.queue.pop(0)
        return item.get("message"), item.get("error")

    async def consume_many(
        self, max_records: int, timeout_ms: int
    ) -> tuple[list[TestMessage], list[str]]:
        batch: list[TestMessage] = []
        errors: list[str] = []

        for _ in range(min(max_records, len(self.queue))):
            item = self.queue.pop(0)
            if "message" in item:
                batch.append(item["message"])
            elif "error" in item:
                errors.append(item["error"])
        return batch, errors

    async def get_lag(self) -> int:
        return 0


class DummyProducer:
    """Simulates a Kafka producer."""

    def __init__(self) -> None:
        self.start = AsyncMock()
        self.stop = AsyncMock()
        self.get_producer = AsyncMock()
        self.produce_one = AsyncMock()
