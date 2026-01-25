from unittest.mock import AsyncMock, MagicMock

import pytest
from aiokafka.errors import KafkaTimeoutError
from aiokafka.structs import TopicPartition
from bot_detector.kafka.core.base_consumer import BaseConsumer
from bot_detector.kafka.core.base_producer import BaseProducer
from bot_detector.kafka.core.settings import Settings
from pydantic import BaseModel

# ===== BaseConsumer Tests =====


class SampleMessage(BaseModel):
    name: str
    player_id: str


@pytest.mark.asyncio
async def test_base_consumer_valid_initialization():
    """Test that BaseConsumer initializes with valid parameters."""
    consumer = BaseConsumer[SampleMessage](
        topic="test.topic",
        group_id="test-group",
        bootstrap_servers="localhost:9092",
        deserializer=SampleMessage.model_validate,
    )
    assert consumer.topic == "test.topic"
    assert consumer.deserializer == SampleMessage.model_validate


@pytest.mark.asyncio
async def test_base_consumer_auto_commit_disabled():
    """Test that enable_auto_commit parameter is respected."""
    consumer = BaseConsumer[SampleMessage](
        topic="test.topic",
        group_id="test-group",
        bootstrap_servers="localhost:9092",
        deserializer=SampleMessage.model_validate,
        enable_auto_commit=False,
    )
    assert consumer._consumer is not None


@pytest.mark.asyncio
async def test_base_consumer_consume_one_success():
    """Test successful consumption of a single message."""
    consumer = BaseConsumer[SampleMessage](
        topic="test.topic",
        group_id="test-group",
        bootstrap_servers="localhost:9092",
        deserializer=SampleMessage.model_validate,
    )

    message_data = {"player_id": "123", "name": "test"}
    mock_consumer_record = MagicMock()
    mock_consumer_record.value = message_data

    mock_aio_consumer = AsyncMock()
    mock_aio_consumer.getone = AsyncMock(return_value=mock_consumer_record)
    consumer._consumer = mock_aio_consumer

    result, error = await consumer.consume_one()

    assert result is not None
    assert result.player_id == "123"
    assert result.name == "test"
    assert error is None


@pytest.mark.asyncio
async def test_base_consumer_consume_one_kafka_error():
    """Test that Kafka errors are returned as error strings."""
    consumer = BaseConsumer[SampleMessage](
        topic="test.topic",
        group_id="test-group",
        bootstrap_servers="localhost:9092",
        deserializer=SampleMessage.model_validate,
    )

    mock_aio_consumer = AsyncMock()
    mock_aio_consumer.getone = AsyncMock(
        side_effect=Exception("Kafka connection error")
    )
    consumer._consumer = mock_aio_consumer

    result, error = await consumer.consume_one()

    assert result is None
    assert error is not None
    assert "Kafka connection error" in error
    assert "Kafka getone error" in error


@pytest.mark.asyncio
async def test_base_consumer_consume_one_non_dict_value():
    """Test that non-dict values are handled gracefully."""
    consumer = BaseConsumer[SampleMessage](
        topic="test.topic",
        group_id="test-group",
        bootstrap_servers="localhost:9092",
        deserializer=SampleMessage.model_validate,
    )

    mock_consumer_record = MagicMock()
    mock_consumer_record.value = "not a dict"

    mock_aio_consumer = AsyncMock()
    mock_aio_consumer.getone = AsyncMock(return_value=mock_consumer_record)
    consumer._consumer = mock_aio_consumer

    result, error = await consumer.consume_one()

    assert result is None
    assert error == "Message value is not a dict"


@pytest.mark.asyncio
async def test_base_consumer_consume_one_validation_error():
    """Test that Pydantic validation errors are caught and returned."""
    consumer = BaseConsumer[SampleMessage](
        topic="test.topic",
        group_id="test-group",
        bootstrap_servers="localhost:9092",
        deserializer=SampleMessage.model_validate,
    )

    invalid_message = {"player_id": 123, "name": "test"}
    mock_consumer_record = MagicMock()
    mock_consumer_record.value = invalid_message

    mock_aio_consumer = AsyncMock()
    mock_aio_consumer.getone = AsyncMock(return_value=mock_consumer_record)
    consumer._consumer = mock_aio_consumer

    result, error = await consumer.consume_one()

    assert result is None
    assert error is not None
    assert "Validation error" in error


@pytest.mark.asyncio
async def test_base_consumer_consume_many_success():
    """Test successful batch consumption."""
    consumer = BaseConsumer[SampleMessage](
        topic="test.topic",
        group_id="test-group",
        bootstrap_servers="localhost:9092",
        deserializer=SampleMessage.model_validate,
    )

    mock_records = [
        MagicMock(value={"player_id": str(i), "name": f"player_{i}_unique_{id(i)}"})
        for i in range(2)
    ]

    call_count = [0]

    async def getmany_side_effect(timeout_ms, max_records):
        """Return records once, then empty dict."""
        call_count[0] += 1
        if call_count[0] == 1:
            return {TopicPartition("test.topic", 0): mock_records}
        return {}  # Empty on subsequent calls

    mock_aio_consumer = AsyncMock()
    mock_aio_consumer.getmany = AsyncMock(side_effect=getmany_side_effect)
    consumer._consumer = mock_aio_consumer

    values, errors = await consumer.consume_many(max_records=10, timeout_ms=1000)

    assert len(values) == 2
    assert len(errors) == 0
    assert all(isinstance(v, SampleMessage) for v in values)


@pytest.mark.asyncio
async def test_base_consumer_consume_many_getmany_error():
    """Test that getmany errors stop consumption and return errors."""
    consumer = BaseConsumer[SampleMessage](
        topic="test.topic",
        group_id="test-group",
        bootstrap_servers="localhost:9092",
        deserializer=SampleMessage.model_validate,
    )

    mock_aio_consumer = AsyncMock()
    mock_aio_consumer.getmany = AsyncMock(side_effect=Exception("Kafka getmany error"))
    consumer._consumer = mock_aio_consumer

    values, errors = await consumer.consume_many(max_records=10, timeout_ms=1000)

    assert len(values) == 0
    assert len(errors) == 1
    assert "Kafka getmany error" in errors[0]


@pytest.mark.asyncio
async def test_base_consumer_get_lag_no_partitions():
    """Test get_lag when topic has no partitions."""
    consumer = BaseConsumer[SampleMessage](
        topic="test.topic",
        group_id="test-group",
        bootstrap_servers="localhost:9092",
        deserializer=SampleMessage.model_validate,
    )

    mock_aio_consumer = AsyncMock()
    mock_aio_consumer.partitions_for_topic = MagicMock(return_value=None)
    consumer._consumer = mock_aio_consumer

    lag = await consumer.get_lag()

    assert lag == 0


@pytest.mark.asyncio
async def test_base_consumer_get_lag_committed_none():
    """Test get_lag when committed offset is None (new consumer)."""
    consumer = BaseConsumer[SampleMessage](
        topic="test.topic",
        group_id="test-group",
        bootstrap_servers="localhost:9092",
        deserializer=SampleMessage.model_validate,
    )

    tp = TopicPartition("test.topic", 0)
    mock_aio_consumer = AsyncMock()
    mock_aio_consumer.partitions_for_topic = MagicMock(return_value={0})
    mock_aio_consumer.committed = AsyncMock(return_value=None)
    mock_aio_consumer.end_offsets = AsyncMock(return_value={tp: 100})
    consumer._consumer = mock_aio_consumer

    lag = await consumer.get_lag()

    assert lag == 100


@pytest.mark.asyncio
async def test_base_consumer_get_lag_committed_zero():
    """Test get_lag when committed offset is 0."""
    consumer = BaseConsumer[SampleMessage](
        topic="test.topic",
        group_id="test-group",
        bootstrap_servers="localhost:9092",
        deserializer=SampleMessage.model_validate,
    )

    tp = TopicPartition("test.topic", 0)
    mock_aio_consumer = AsyncMock()
    mock_aio_consumer.partitions_for_topic = MagicMock(return_value={0})
    mock_aio_consumer.committed = AsyncMock(return_value=0)
    mock_aio_consumer.end_offsets = AsyncMock(return_value={tp: 50})
    consumer._consumer = mock_aio_consumer

    lag = await consumer.get_lag()

    assert lag == 50


@pytest.mark.asyncio
async def test_base_consumer_lifecycle():
    """Test start/stop lifecycle methods."""
    consumer = BaseConsumer[SampleMessage](
        topic="test.topic",
        group_id="test-group",
        bootstrap_servers="localhost:9092",
        deserializer=SampleMessage.model_validate,
    )

    mock_aio_consumer = AsyncMock()
    consumer._consumer = mock_aio_consumer

    await consumer.start()
    mock_aio_consumer.start.assert_called_once()

    await consumer.commit()
    mock_aio_consumer.commit.assert_called_once()

    await consumer.stop()
    mock_aio_consumer.stop.assert_called_once()


@pytest.mark.asyncio
async def test_base_consumer_get_consumer():
    """Test get_consumer returns the underlying AIOKafkaConsumer."""
    consumer = BaseConsumer[SampleMessage](
        topic="test.topic",
        group_id="test-group",
        bootstrap_servers="localhost:9092",
        deserializer=SampleMessage.model_validate,
    )

    mock_aio_consumer = AsyncMock()
    consumer._consumer = mock_aio_consumer

    result = await consumer.get_consumer()
    assert result is mock_aio_consumer


# ===== BaseProducer Tests =====


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
