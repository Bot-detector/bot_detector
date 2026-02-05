import pytest
from bot_detector.event_queue.adapters.memory import (
    InMemoryConfig,
    InMemoryConsumerAdapter,
)
from pydantic import BaseModel


class PlayerScraped(BaseModel):
    id: int
    username: str
    score: int


@pytest.mark.asyncio
async def test_consumer_get_one_empty():
    config = InMemoryConfig(maxsize=10)
    adapter = InMemoryConsumerAdapter(PlayerScraped, config)

    result = await adapter.get_one()

    assert result is None


@pytest.mark.asyncio
async def test_consumer_get_one_invalid_message():
    config = InMemoryConfig(maxsize=10)
    adapter = InMemoryConsumerAdapter(PlayerScraped, config)

    adapter._queue.put_nowait({"id": 1})

    result = await adapter.get_one()

    assert result is None


@pytest.mark.asyncio
async def test_consumer_get_many_filters_invalid():
    config = InMemoryConfig(maxsize=10)
    adapter = InMemoryConsumerAdapter(PlayerScraped, config)

    adapter._queue.put_nowait({"id": 1, "username": "Alice", "score": 100})
    adapter._queue.put_nowait({"id": 2})
    adapter._queue.put_nowait({"id": 3, "username": "Bob", "score": 200})

    result = await adapter.get_many(3)

    assert [item.username for item in result] == ["Alice", "Bob"]


@pytest.mark.asyncio
async def test_consumer_get_many_stops_on_empty():
    config = InMemoryConfig(maxsize=10)
    adapter = InMemoryConsumerAdapter(PlayerScraped, config)

    adapter._queue.put_nowait({"id": 1, "username": "Alice", "score": 100})

    result = await adapter.get_many(2)

    assert [item.username for item in result] == ["Alice"]


@pytest.mark.asyncio
async def test_consumer_commit_after_get():
    config = InMemoryConfig(maxsize=10)
    adapter = InMemoryConsumerAdapter(PlayerScraped, config)

    adapter._queue.put_nowait({"id": 1, "username": "Alice", "score": 100})

    await adapter.get_one()

    result = await adapter.commit()

    assert result is None
