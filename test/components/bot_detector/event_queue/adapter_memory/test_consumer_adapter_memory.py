import pytest
from bot_detector.event_queue.adapters.memory import (
    InMemoryConfig,
    InMemoryConsumerAdapter,
)
from prometheus_client import REGISTRY
from pydantic import BaseModel, ValidationError


class PlayerScraped(BaseModel):
    id: int
    username: str
    score: int


def _skipped_total() -> float | None:
    return REGISTRY.get_sample_value("event_queue_messages_skipped_total")


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

    # parity with the kafka backend: invalid payloads surface as error
    # values, never as a silent None (None means "queue empty")
    result = await adapter.get_one()

    assert isinstance(result, ValidationError)


@pytest.mark.asyncio
async def test_consumer_get_many_filters_invalid():
    config = InMemoryConfig(maxsize=10)
    adapter = InMemoryConsumerAdapter(PlayerScraped, config)

    adapter._queue.put_nowait({"id": 1, "username": "Alice", "score": 100})
    adapter._queue.put_nowait({"id": 2})
    adapter._queue.put_nowait({"id": 3, "username": "Bob", "score": 200})

    before = _skipped_total()
    result = await adapter.get_many(3)

    assert [item.username for item in result] == ["Alice", "Bob"]
    assert _skipped_total() == (before or 0) + 1


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


@pytest.mark.asyncio
async def test_consumer_commit_without_get_returns_none():
    config = InMemoryConfig(maxsize=10)
    adapter = InMemoryConsumerAdapter(PlayerScraped, config)

    # commit must never raise, even with nothing dequeued
    # (task_done() used to raise ValueError here)
    result = await adapter.commit()

    assert result is None
