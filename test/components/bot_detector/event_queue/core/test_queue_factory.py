import pytest
from bot_detector.event_queue.adapters.memory import InMemoryAdapter, InMemoryConfig
from bot_detector.event_queue.core.event_queue import Queue, QueueConsumer, QueueProducer
from bot_detector.event_queue.factory import InvalidConfig, QueueFactory
from pydantic import BaseModel


class PlayerScraped(BaseModel):
    id: int
    username: str
    score: int


def test_queue_factory_creates_memory_queue():
    config = InMemoryConfig(maxsize=5)

    queue = QueueFactory.create_queue(
        PlayerScraped,
        queue_type="queue",
        backend_type="memory",
        config=config,
    )

    assert isinstance(queue, Queue)
    assert isinstance(queue._backend, InMemoryAdapter)


def test_queue_factory_creates_memory_producer():
    config = InMemoryConfig(maxsize=5)

    queue = QueueFactory.create_queue(
        PlayerScraped,
        queue_type="producer",
        backend_type="memory",
        config=config,
    )

    assert isinstance(queue, QueueProducer)


def test_queue_factory_creates_memory_consumer():
    config = InMemoryConfig(maxsize=5)

    queue = QueueFactory.create_queue(
        PlayerScraped,
        queue_type="consumer",
        backend_type="memory",
        config=config,
    )

    assert isinstance(queue, QueueConsumer)


def test_queue_factory_returns_error_for_unknown_backend():
    config = InMemoryConfig(maxsize=5)

    queue = QueueFactory.create_queue(
        PlayerScraped,
        queue_type="queue",
        backend_type="unknown",
        config=config,
    )

    assert isinstance(queue, ValueError)
    assert str(queue) == "Unknown backend_type: unknown"


def test_queue_factory_returns_error_for_unknown_queue_type():
    config = InMemoryConfig(maxsize=5)

    queue = QueueFactory.create_queue(
        PlayerScraped,
        queue_type="invalid",
        backend_type="memory",
        config=config,
    )

    assert isinstance(queue, ValueError)
    assert str(queue) == "Unknown queue_type: memory"


def test_queue_factory_raises_invalid_config():
    with pytest.raises(InvalidConfig, match="Expected InMemoryConfig"):
        QueueFactory.create_queue(
            PlayerScraped,
            queue_type="queue",
            backend_type="memory",
            config=object(),
        )


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
