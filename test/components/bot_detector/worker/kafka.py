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
        {"error": Exception(...)}      -> a consumer error
    """

    def __init__(self, queue: list[dict] | None = None) -> None:
        self.queue = queue or []
        self.start = AsyncMock()
        self.stop = AsyncMock()
        self.commit = AsyncMock()
        self.get_consumer = AsyncMock()

    async def get_one(self) -> TestMessage | None | Exception:
        if not self.queue:
            return None
        item = self.queue.pop(0)
        return item.get("message") or item.get("error")

    async def get_many(self, count: int) -> list[TestMessage] | Exception:
        batch: list[TestMessage] = []
        for _ in range(min(count, len(self.queue))):
            item = self.queue.pop(0)
            if "message" in item:
                batch.append(item["message"])
            elif "error" in item:
                return item["error"]
        return batch

    async def get_lag(self) -> int:
        return 0


class DummyProducer:
    """Simulates a Kafka producer."""

    def __init__(self) -> None:
        self.start = AsyncMock()
        self.stop = AsyncMock()
        self.get_producer = AsyncMock()
        self.put = AsyncMock()


class DummyQueue(DummyConsumer, DummyProducer):
    """Simulates a Queue with both consumer and producer capabilities."""

    def __init__(self, queue: list[dict] | None = None) -> None:
        DummyConsumer.__init__(self, queue=queue)
        DummyProducer.__init__(self)
