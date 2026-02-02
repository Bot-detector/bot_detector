from unittest.mock import AsyncMock, MagicMock

import pytest
from aiokafka.structs import TopicPartition
from bot_detector.kafka.core.base_consumer import BaseConsumer
from pydantic import BaseModel


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
