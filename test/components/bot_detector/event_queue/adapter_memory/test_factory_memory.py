import pytest
from bot_detector.event_queue.adapters.memory import InMemoryConfig
from bot_detector.event_queue.core.event_queue import Queue
from bot_detector.event_queue.factory import QueueFactory
from pydantic import BaseModel


class PlayerScraped(BaseModel):
    id: int
    username: str
    score: int


@pytest.mark.asyncio
async def test_queue_factory_memory_end_to_end():
    config = InMemoryConfig(maxsize=5)
    queue = QueueFactory.create_queue(
        PlayerScraped,
        queue_type="queue",
        backend_type="memory",
        config=config,
    )

    assert isinstance(queue, Queue)

    await queue.start()
    await queue.put(
        [
            PlayerScraped(id=1, username="Alice", score=100),
            PlayerScraped(id=2, username="Bob", score=200),
        ]
    )
    one = await queue.get_one()
    many = await queue.get_many(2)
    await queue.stop()

    assert one == PlayerScraped(id=1, username="Alice", score=100)
    assert [item.username for item in many] == ["Bob"]
