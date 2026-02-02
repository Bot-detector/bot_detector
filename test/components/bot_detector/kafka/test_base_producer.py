from unittest.mock import AsyncMock, MagicMock

import pytest
from aiokafka.errors import KafkaTimeoutError
from bot_detector.kafka.core.base_producer import BaseProducer
from bot_detector.kafka.core.settings import Settings
from pydantic import BaseModel

# ===== BaseConsumer Tests =====


class SampleMessage(BaseModel):
    name: str
    player_id: str


@pytest.mark.asyncio
async def test_base_producer_valid_initialization():
    """Test that BaseProducer initializes with valid parameters."""
    producer = BaseProducer[SampleMessage](
        bootstrap_servers="localhost:9092",
        topic="test.topic",
    )
    assert producer.topic == "test.topic"
    assert producer._producer is not None


@pytest.mark.asyncio
async def test_base_producer_initialization_without_topic():
    """Test that BaseProducer can be initialized without a default topic."""
    producer = BaseProducer[SampleMessage](
        bootstrap_servers="localhost:9092",
    )
    assert producer.topic is None
    assert producer._producer is not None


@pytest.mark.asyncio
async def test_base_producer_produce_one_success():
    """Test successful message production."""
    producer = BaseProducer[SampleMessage](
        bootstrap_servers="localhost:9092",
        topic="test.topic",
    )

    message = SampleMessage(player_id="123", name="test")
    mock_aio_producer = AsyncMock()
    mock_aio_producer.send = AsyncMock(return_value=MagicMock())
    producer._producer = mock_aio_producer

    await producer.produce_one(message)

    mock_aio_producer.send.assert_called_once()
    call_kwargs = mock_aio_producer.send.call_args.kwargs
    assert call_kwargs["topic"] == "test.topic"
    assert call_kwargs["key"] is None
    assert call_kwargs["value"] == {"player_id": "123", "name": "test"}


@pytest.mark.asyncio
async def test_base_producer_produce_one_missing_topic():
    """Test that missing topic raises ValueError."""
    producer = BaseProducer[SampleMessage](
        bootstrap_servers="localhost:9092",
    )

    message = SampleMessage(player_id="123", name="test")

    with pytest.raises(ValueError, match="Topic must be specified"):
        await producer.produce_one(message)


@pytest.mark.asyncio
async def test_base_producer_produce_one_kafka_timeout_retry():
    """Test that KafkaTimeoutError triggers retry logic.
    With max_retries=5, expects 1 initial attempt + 5 retries = 6 total calls.
    """
    producer = BaseProducer[SampleMessage](
        bootstrap_servers="localhost:9092",
        topic="test.topic",
    )

    message = SampleMessage(player_id="123", name="test")
    mock_aio_producer = AsyncMock()
    mock_aio_producer.send = AsyncMock(side_effect=KafkaTimeoutError())
    producer._producer = mock_aio_producer

    await producer.produce_one(message)

    # 1 initial attempt + 5 retries = 6 total calls before giving up
    assert mock_aio_producer.send.call_count == 6


@pytest.mark.asyncio
async def test_base_producer_produce_one_with_partition_key():
    """Test that partition_key is passed through correctly."""
    producer = BaseProducer[SampleMessage](
        bootstrap_servers="localhost:9092",
        topic="test.topic",
    )

    message = SampleMessage(player_id="123", name="test")
    mock_aio_producer = AsyncMock()
    mock_aio_producer.send = AsyncMock(return_value=MagicMock())
    producer._producer = mock_aio_producer

    await producer.produce_one(message, partition_key=b"partition_1")

    mock_aio_producer.send.assert_called_once()
    call_kwargs = mock_aio_producer.send.call_args.kwargs
    assert call_kwargs["topic"] == "test.topic"
    assert call_kwargs["key"] == b"partition_1"
    assert call_kwargs["value"] == {"player_id": "123", "name": "test"}


@pytest.mark.asyncio
async def test_base_producer_produce_one_topic_override():
    """Test that topic parameter overrides the default topic."""
    producer = BaseProducer[SampleMessage](
        bootstrap_servers="localhost:9092",
        topic="default.topic",
    )

    message = SampleMessage(player_id="123", name="test")
    mock_aio_producer = AsyncMock()
    mock_aio_producer.send = AsyncMock(return_value=MagicMock())
    producer._producer = mock_aio_producer

    await producer.produce_one(message, topic="override.topic")

    mock_aio_producer.send.assert_called_once()
    call_kwargs = mock_aio_producer.send.call_args.kwargs
    assert call_kwargs["topic"] == "override.topic"
    assert call_kwargs["value"] == {"player_id": "123", "name": "test"}


@pytest.mark.asyncio
async def test_base_producer_lifecycle():
    """Test start/stop lifecycle methods."""
    producer = BaseProducer[SampleMessage](
        bootstrap_servers="localhost:9092",
        topic="test.topic",
    )

    mock_aio_producer = AsyncMock()
    producer._producer = mock_aio_producer

    await producer.start()
    mock_aio_producer.start.assert_called_once()

    await producer.stop()
    mock_aio_producer.stop.assert_called_once()


@pytest.mark.asyncio
async def test_base_producer_get_producer():
    """Test get_producer returns the underlying AIOKafkaProducer."""
    producer = BaseProducer[SampleMessage](
        bootstrap_servers="localhost:9092",
        topic="test.topic",
    )

    mock_aio_producer = AsyncMock()
    producer._producer = mock_aio_producer

    result = await producer.get_producer()
    assert result is mock_aio_producer


# ===== Settings Tests =====


@pytest.mark.parametrize(
    "env_value, expected_servers",
    [
        ("localhost:9092", "localhost:9092"),
        ("broker1:9092,broker2:9092", "broker1:9092,broker2:9092"),
    ],
)
def test_settings_from_env(env_value, expected_servers, monkeypatch):
    """Test that Settings reads KAFKA_BOOTSTRAP_SERVERS from environment."""
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", env_value)

    settings = Settings()

    assert settings.KAFKA_BOOTSTRAP_SERVERS == expected_servers


def test_settings_missing_env(monkeypatch):
    """Test that Settings raises error when env var is missing."""
    monkeypatch.delenv("KAFKA_BOOTSTRAP_SERVERS", raising=False)

    with pytest.raises(Exception):
        Settings()
