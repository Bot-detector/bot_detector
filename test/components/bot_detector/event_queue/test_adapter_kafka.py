from unittest.mock import AsyncMock, patch

import orjson
import pytest
from aiokafka.errors import KafkaTimeoutError
from bot_detector.event_queue.adapters.kafka import (
    AIOKafkaConsumerAdapter,
    AIOKafkaProducerAdapter,
    KafkaConfig,
    KafkaConsumerConfig,
    KafkaProducerConfig,
)
from bot_detector.event_queue.core.errors import (
    ConsumerConfigError,
    ConsumerFetchError,
    ConsumerNotStartedError,
    MessageTypeError,
    ProducerConfigError,
    ProducerNotStartedError,
)
from pydantic import BaseModel


class PlayerScraped(BaseModel):
    id: int
    username: str
    score: int


@pytest.mark.asyncio
async def test_producer_put_success():
    config = KafkaConfig(
        topic="players",
        bootstrap_servers="localhost:9092",
        consumer=False,
        producer=True,
        consumer_config=None,
        producer_config=KafkaProducerConfig(partition_key_fn=lambda: "1"),
    )
    adapter = AIOKafkaProducerAdapter(PlayerScraped, config)

    with patch(
        "bot_detector.event_queue.adapters.kafka.adapter.AIOKafkaProducer"
    ) as mock_producer_class:
        mock_producer = mock_producer_class.return_value
        mock_producer.start = AsyncMock()
        mock_producer.send = AsyncMock()
        mock_producer.stop = AsyncMock()

        await adapter.start()
        await adapter.put([PlayerScraped(id=1, username="Alice", score=100)])

        mock_producer.send.assert_called_once()


@pytest.mark.asyncio
async def test_producer_start_stop():
    config = KafkaConfig(
        topic="players",
        bootstrap_servers="localhost:9092",
        consumer=False,
        producer=True,
        consumer_config=None,
        producer_config=KafkaProducerConfig(partition_key_fn=lambda: "1"),
    )
    adapter = AIOKafkaProducerAdapter(PlayerScraped, config)

    with patch(
        "bot_detector.event_queue.adapters.kafka.adapter.AIOKafkaProducer"
    ) as mock_producer_class:
        mock_producer = mock_producer_class.return_value
        mock_producer.start = AsyncMock()
        mock_producer.stop = AsyncMock()

        await adapter.start()
        await adapter.stop()

        mock_producer.start.assert_awaited_once()
        mock_producer.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_producer_batch_messages():
    config = KafkaConfig(
        topic="players",
        bootstrap_servers="localhost:9092",
        consumer=False,
        producer=True,
        consumer_config=None,
        producer_config=KafkaProducerConfig(partition_key_fn=lambda: "1"),
    )
    adapter = AIOKafkaProducerAdapter(PlayerScraped, config)

    with patch(
        "bot_detector.event_queue.adapters.kafka.adapter.AIOKafkaProducer"
    ) as mock_producer_class:
        mock_producer = mock_producer_class.return_value
        mock_producer.start = AsyncMock()
        mock_producer.send = AsyncMock()
        mock_producer.stop = AsyncMock()

        await adapter.start()
        await adapter.put(
            [
                PlayerScraped(id=1, username="Alice", score=100),
                PlayerScraped(id=2, username="Bob", score=200),
            ]
        )

        assert mock_producer.send.call_count == 2


@pytest.mark.asyncio
async def test_producer_custom_partition_key():
    config = KafkaConfig(
        topic="players",
        bootstrap_servers="localhost:9092",
        consumer=False,
        producer=True,
        consumer_config=None,
        producer_config=KafkaProducerConfig(partition_key_fn=lambda: "1"),
    )
    adapter = AIOKafkaProducerAdapter(PlayerScraped, config)

    with patch(
        "bot_detector.event_queue.adapters.kafka.adapter.AIOKafkaProducer"
    ) as mock_producer_class:
        mock_producer = mock_producer_class.return_value
        mock_producer.start = AsyncMock()
        mock_producer.send = AsyncMock()
        mock_producer.stop = AsyncMock()

        await adapter.start()
        await adapter.put([PlayerScraped(id=9, username="Alice", score=100)])

        expected_key = b"1"
        mock_producer.send.assert_called_once_with(
            topic="players",
            value=PlayerScraped(id=9, username="Alice", score=100).model_dump(),
            key=expected_key,
        )


@pytest.mark.asyncio
async def test_producer_serialization():
    config = KafkaConfig(
        topic="players",
        bootstrap_servers="localhost:9092",
        consumer=False,
        producer=True,
        consumer_config=None,
        producer_config=KafkaProducerConfig(partition_key_fn=lambda: "1"),
    )
    adapter = AIOKafkaProducerAdapter(PlayerScraped, config)

    with patch(
        "bot_detector.event_queue.adapters.kafka.adapter.AIOKafkaProducer"
    ) as mock_producer_class:
        mock_producer = mock_producer_class.return_value
        mock_producer.start = AsyncMock()

        await adapter.start()

        serializer = mock_producer_class.call_args.kwargs["value_serializer"]
        payload = PlayerScraped(id=1, username="Alice", score=100).model_dump()
        assert serializer(payload) == orjson.dumps(payload)


@pytest.mark.asyncio
async def test_consumer_get_one_empty():
    config = KafkaConfig(
        topic="players",
        bootstrap_servers="localhost:9092",
        consumer=True,
        producer=False,
        consumer_config=KafkaConsumerConfig(group_id="group"),
        producer_config=None,
    )
    adapter = AIOKafkaConsumerAdapter(PlayerScraped, config)

    adapter.consumer = AsyncMock()
    adapter.consumer.getone = AsyncMock(return_value=None)

    result = await adapter.get_one()
    assert result is None


@pytest.mark.asyncio
async def test_consumer_start_stop():
    config = KafkaConfig(
        topic="players",
        bootstrap_servers="localhost:9092",
        consumer=True,
        producer=False,
        consumer_config=KafkaConsumerConfig(group_id="group"),
        producer_config=None,
    )
    adapter = AIOKafkaConsumerAdapter(PlayerScraped, config)

    with patch(
        "bot_detector.event_queue.adapters.kafka.adapter.AIOKafkaConsumer"
    ) as mock_consumer_class:
        mock_consumer = mock_consumer_class.return_value
        mock_consumer.start = AsyncMock()
        mock_consumer.stop = AsyncMock()

        await adapter.start()
        await adapter.stop()

        mock_consumer.start.assert_awaited_once()
        mock_consumer.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_consumer_get_batch():
    config = KafkaConfig(
        topic="players",
        bootstrap_servers="localhost:9092",
        consumer=True,
        producer=False,
        consumer_config=KafkaConsumerConfig(group_id="group"),
        producer_config=None,
    )
    adapter = AIOKafkaConsumerAdapter(PlayerScraped, config)

    fake_record_one = AsyncMock()
    fake_record_one.value = {"id": 1, "username": "Alice", "score": 100}
    fake_record_two = AsyncMock()
    fake_record_two.value = {"id": 2, "username": "Bob", "score": 200}

    adapter.consumer = AsyncMock()
    adapter.consumer.getmany = AsyncMock(
        return_value={0: [fake_record_one, fake_record_two]}
    )

    result = await adapter.get_many(2)
    assert not isinstance(result, Exception)
    assert [item.username for item in result] == ["Alice", "Bob"]


@pytest.mark.asyncio
async def test_consumer_multiple_messages():
    config = KafkaConfig(
        topic="players",
        bootstrap_servers="localhost:9092",
        consumer=True,
        producer=False,
        consumer_config=KafkaConsumerConfig(group_id="group"),
        producer_config=None,
    )
    adapter = AIOKafkaConsumerAdapter(PlayerScraped, config)

    fake_record_one = AsyncMock()
    fake_record_one.value = {"id": 1, "username": "Alice", "score": 100}
    fake_record_two = AsyncMock()
    fake_record_two.value = {"id": 2, "username": "Bob", "score": 200}

    adapter.consumer = AsyncMock()
    adapter.consumer.getone = AsyncMock(side_effect=[fake_record_one, fake_record_two])

    first = await adapter.get_one()
    second = await adapter.get_one()
    assert isinstance(first, PlayerScraped)
    assert isinstance(second, PlayerScraped)
    assert first.username == "Alice"
    assert second.username == "Bob"


@pytest.mark.asyncio
async def test_producer_send_failure():
    config = KafkaConfig(
        topic="players",
        bootstrap_servers="localhost:9092",
        consumer=False,
        producer=True,
        consumer_config=None,
        producer_config=KafkaProducerConfig(
            partition_key_fn=lambda: "1",
            MAX_PRODUCE_RETRIES=1,
        ),
    )
    adapter = AIOKafkaProducerAdapter(PlayerScraped, config)

    with (
        patch(
            "bot_detector.event_queue.adapters.kafka.adapter.AIOKafkaProducer"
        ) as mock_producer_class,
        patch(
            "bot_detector.event_queue.adapters.kafka.adapter.asyncio.sleep",
            new=AsyncMock(),
        ),
    ):
        mock_producer = mock_producer_class.return_value
        mock_producer.start = AsyncMock()
        mock_producer.send = AsyncMock(side_effect=KafkaTimeoutError("fail"))
        mock_producer.stop = AsyncMock()

        await adapter.start()
        result = await adapter.put([PlayerScraped(id=1, username="Alice", score=100)])

        assert isinstance(result, KafkaTimeoutError)


@pytest.mark.asyncio
async def test_consumer_connection_error():
    config = KafkaConfig(
        topic="players",
        bootstrap_servers="localhost:9092",
        consumer=True,
        producer=False,
        consumer_config=KafkaConsumerConfig(group_id="group"),
        producer_config=None,
    )
    adapter = AIOKafkaConsumerAdapter(PlayerScraped, config)

    adapter.consumer = AsyncMock()
    adapter.consumer.getone = AsyncMock(side_effect=Exception("boom"))

    result = await adapter.get_one()
    assert isinstance(result, ConsumerFetchError)
    assert isinstance(result.cause, Exception)


@pytest.mark.asyncio
async def test_producer_put_without_start():
    config = KafkaConfig(
        topic="players",
        bootstrap_servers="localhost:9092",
        consumer=False,
        producer=True,
        consumer_config=None,
        producer_config=KafkaProducerConfig(partition_key_fn=lambda: "1"),
    )
    adapter = AIOKafkaProducerAdapter(PlayerScraped, config)

    result = await adapter.put([PlayerScraped(id=1, username="Alice", score=100)])

    assert isinstance(result, ProducerNotStartedError)


@pytest.mark.asyncio
async def test_consumer_get_one_without_start():
    config = KafkaConfig(
        topic="players",
        bootstrap_servers="localhost:9092",
        consumer=True,
        producer=False,
        consumer_config=KafkaConsumerConfig(group_id="group"),
        producer_config=None,
    )
    adapter = AIOKafkaConsumerAdapter(PlayerScraped, config)

    result = await adapter.get_one()

    assert isinstance(result, ConsumerNotStartedError)


@pytest.mark.asyncio
async def test_consumer_invalid_message_type():
    config = KafkaConfig(
        topic="players",
        bootstrap_servers="localhost:9092",
        consumer=True,
        producer=False,
        consumer_config=KafkaConsumerConfig(group_id="group"),
        producer_config=None,
    )
    adapter = AIOKafkaConsumerAdapter(PlayerScraped, config)

    fake_record = AsyncMock()
    fake_record.value = ["not", "a", "dict"]

    adapter.consumer = AsyncMock()
    adapter.consumer.getone = AsyncMock(return_value=fake_record)

    result = await adapter.get_one()

    assert isinstance(result, MessageTypeError)


@pytest.mark.asyncio
async def test_producer_put_without_config():
    config = KafkaConfig.model_construct(
        topic="players",
        bootstrap_servers="localhost:9092",
        consumer=False,
        producer=True,
        consumer_config=None,
        producer_config=None,
    )
    adapter = AIOKafkaProducerAdapter(PlayerScraped, config)
    adapter.producer = AsyncMock()

    result = await adapter.put([PlayerScraped(id=1, username="Alice", score=100)])

    assert isinstance(result, ProducerConfigError)


@pytest.mark.asyncio
async def test_consumer_get_many_without_config():
    config = KafkaConfig.model_construct(
        topic="players",
        bootstrap_servers="localhost:9092",
        consumer=True,
        producer=False,
        consumer_config=None,
        producer_config=None,
    )
    adapter = AIOKafkaConsumerAdapter(PlayerScraped, config)
    adapter.consumer = AsyncMock()

    result = await adapter.get_many(1)

    assert isinstance(result, ConsumerConfigError)


@pytest.mark.asyncio
async def test_consumer_start_without_config():
    config = KafkaConfig.model_construct(
        topic="players",
        bootstrap_servers="localhost:9092",
        consumer=True,
        producer=False,
        consumer_config=None,
        producer_config=None,
    )
    adapter = AIOKafkaConsumerAdapter(PlayerScraped, config)

    with pytest.raises(ConsumerConfigError):
        await adapter.start()


@pytest.mark.asyncio
async def test_consumer_get_many_connection_error():
    config = KafkaConfig(
        topic="players",
        bootstrap_servers="localhost:9092",
        consumer=True,
        producer=False,
        consumer_config=KafkaConsumerConfig(group_id="group"),
        producer_config=None,
    )
    adapter = AIOKafkaConsumerAdapter(PlayerScraped, config)
    adapter.consumer = AsyncMock()
    adapter.consumer.getmany = AsyncMock(side_effect=Exception("boom"))

    result = await adapter.get_many(1)

    assert isinstance(result, ConsumerFetchError)
    assert isinstance(result.cause, Exception)


@pytest.mark.asyncio
async def test_consumer_get_many_invalid_message_type():
    config = KafkaConfig(
        topic="players",
        bootstrap_servers="localhost:9092",
        consumer=True,
        producer=False,
        consumer_config=KafkaConsumerConfig(group_id="group"),
        producer_config=None,
    )
    adapter = AIOKafkaConsumerAdapter(PlayerScraped, config)

    fake_record = AsyncMock()
    fake_record.value = "not-a-dict"

    adapter.consumer = AsyncMock()
    adapter.consumer.getmany = AsyncMock(return_value={0: [fake_record]})

    result = await adapter.get_many(1)

    assert isinstance(result, MessageTypeError)


@pytest.mark.asyncio
async def test_consumer_commit_without_start():
    config = KafkaConfig(
        topic="players",
        bootstrap_servers="localhost:9092",
        consumer=True,
        producer=False,
        consumer_config=KafkaConsumerConfig(group_id="group"),
        producer_config=None,
    )
    adapter = AIOKafkaConsumerAdapter(PlayerScraped, config)

    result = await adapter.commit()

    assert isinstance(result, ConsumerNotStartedError)
