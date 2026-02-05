from unittest.mock import AsyncMock

import pytest
from bot_detector.event_queue.core.event_queue import QueueConsumer
from pydantic import BaseModel


class PlayerScraped(BaseModel):
    id: int
    username: str
    score: int


@pytest.mark.asyncio
async def test_queue_consumer_delegates_to_backend():
    backend = AsyncMock()
    one_message = PlayerScraped(id=1, username="Alice", score=100)
    many_messages = [
        PlayerScraped(id=2, username="Bob", score=200),
        PlayerScraped(id=3, username="Cara", score=300),
    ]
    backend.get_one = AsyncMock(return_value=one_message)
    backend.get_many = AsyncMock(return_value=many_messages)

    queue = QueueConsumer(backend)

    await queue.start()
    one = await queue.get_one()
    many = await queue.get_many(2)
    await queue.stop()

    backend.start.assert_awaited_once()
    backend.get_one.assert_awaited_once()
    backend.get_many.assert_awaited_once_with(2)
    backend.stop.assert_awaited_once()
    assert one == one_message
    assert many == many_messages
