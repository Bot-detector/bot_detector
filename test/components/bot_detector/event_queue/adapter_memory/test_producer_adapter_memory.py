import pytest
from bot_detector.event_queue.adapters.memory import (
    InMemoryConfig,
    InMemoryProducerAdapter,
)
from pydantic import BaseModel


class PlayerScraped(BaseModel):
    id: int
    username: str
    score: int


@pytest.mark.asyncio
async def test_producer_put_enqueues_messages():
    config = InMemoryConfig(maxsize=10)
    adapter = InMemoryProducerAdapter(PlayerScraped, config)

    await adapter.put([PlayerScraped(id=1, username="Alice", score=100)])

    queued = adapter._queue.get_nowait()
    assert queued == PlayerScraped(id=1, username="Alice", score=100)
