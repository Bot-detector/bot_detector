import pytest
from bot_detector.event_queue.adapters.memory import InMemoryAdapter, InMemoryConfig
from pydantic import BaseModel


class PlayerScraped(BaseModel):
    id: int
    username: str
    score: int


@pytest.mark.asyncio
async def test_queue_adapter_wiring():
    adapter = InMemoryAdapter(PlayerScraped, InMemoryConfig(maxsize=10))

    await adapter.start()

    await adapter.put(
        [
            PlayerScraped(id=1, username="Alice", score=100),
            PlayerScraped(id=2, username="Bob", score=200),
        ]
    )

    one = await adapter.get_one()
    many = await adapter.get_many(2)
    await adapter.commit()
    await adapter.stop()

    assert one == PlayerScraped(id=1, username="Alice", score=100)
    assert [item.username for item in many] == ["Bob"]
