from unittest.mock import AsyncMock

import pytest
from bot_detector.event_queue.core.event_queue import QueueProducer
from pydantic import BaseModel


class PlayerScraped(BaseModel):
    id: int
    username: str
    score: int


@pytest.mark.asyncio
async def test_queue_producer_delegates_to_backend():
    backend = AsyncMock()
    queue = QueueProducer(backend)
    message = PlayerScraped(id=1, username="Alice", score=100)

    await queue.start()
    await queue.put([message])
    await queue.stop()

    backend.start.assert_awaited_once()
    backend.put.assert_awaited_once_with([message])
    backend.stop.assert_awaited_once()
