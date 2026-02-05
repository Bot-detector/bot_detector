from unittest.mock import AsyncMock

import pytest
from bot_detector.event_queue.core.event_queue import Queue
from pydantic import BaseModel


class PlayerScraped(BaseModel):
    id: int
    username: str
    score: int


@pytest.mark.asyncio
async def test_queue_delegates_to_backend():
    backend = AsyncMock()
    one_message = PlayerScraped(id=1, username="Alice", score=100)
    many_messages = [PlayerScraped(id=2, username="Bob", score=200)]
    backend.get_one = AsyncMock(return_value=one_message)
    backend.get_many = AsyncMock(return_value=many_messages)

    queue = Queue(backend)

    await queue.start()
    await queue.put([one_message])
    one = await queue.get_one()
    many = await queue.get_many(1)
    await queue.stop()

    backend.start.assert_awaited_once()
    backend.put.assert_awaited_once_with([one_message])
    backend.get_one.assert_awaited_once()
    backend.get_many.assert_awaited_once_with(1)
    backend.stop.assert_awaited_once()
    assert one == one_message
    assert many == many_messages
