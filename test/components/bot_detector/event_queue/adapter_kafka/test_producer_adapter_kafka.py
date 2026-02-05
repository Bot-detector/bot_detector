from unittest.mock import AsyncMock, patch

import orjson
import pytest
from aiokafka.errors import KafkaTimeoutError
from bot_detector.event_queue.adapters.kafka import (
    AIOKafkaProducerAdapter,
    KafkaConfig,
    KafkaProducerConfig,
)
from bot_detector.event_queue.core.errors import (
    ProducerConfigError,
    ProducerNotStartedError,
)
from pydantic import BaseModel


class PlayerScraped(BaseModel):
    id: int
    username: str
    score: int


@pytest.mark.asyncio
async def test_producer_start_stop():
    config = KafkaConfig(
        topic="players",
        bootstrap_servers="localhost:9092",
        consumer=False,
        producer=True,
        consumer_config=None,
        producer_config=KafkaProducerConfig(partition_key_fn=lambda _: "1"),
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
async def test_producer_custom_partition_key():
    config = KafkaConfig(
        topic="players",
        bootstrap_servers="localhost:9092",
        consumer=False,
        producer=True,
        consumer_config=None,
        producer_config=KafkaProducerConfig(partition_key_fn=lambda _: "1"),
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
async def test_producer_partition_key_bytes():
    config = KafkaConfig(
        topic="players",
        bootstrap_servers="localhost:9092",
        consumer=False,
        producer=True,
        consumer_config=None,
        producer_config=KafkaProducerConfig(partition_key_fn=lambda _: b"bytes"),
    )
    adapter = AIOKafkaProducerAdapter(PlayerScraped, config)

    adapter.producer = AsyncMock()
    adapter.producer.send = AsyncMock()

    await adapter.put([PlayerScraped(id=9, username="Alice", score=100)])

    adapter.producer.send.assert_called_once_with(
        topic="players",
        value=PlayerScraped(id=9, username="Alice", score=100).model_dump(),
        key=b"bytes",
    )


@pytest.mark.asyncio
async def test_producer_partition_key_invalid_type():
    config = KafkaConfig(
        topic="players",
        bootstrap_servers="localhost:9092",
        consumer=False,
        producer=True,
        consumer_config=None,
        producer_config=KafkaProducerConfig(partition_key_fn=lambda _: 123),
    )
    adapter = AIOKafkaProducerAdapter(PlayerScraped, config)
    adapter.producer = AsyncMock()
    adapter.producer.send = AsyncMock()

    with pytest.raises(ValueError, match="partition_key_fn must return bytes or str"):
        await adapter.put([PlayerScraped(id=9, username="Alice", score=100)])


@pytest.mark.asyncio
async def test_producer_serialization():
    config = KafkaConfig(
        topic="players",
        bootstrap_servers="localhost:9092",
        consumer=False,
        producer=True,
        consumer_config=None,
        producer_config=KafkaProducerConfig(partition_key_fn=lambda _: "1"),
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
async def test_producer_start_noop_when_existing():
    config = KafkaConfig(
        topic="players",
        bootstrap_servers="localhost:9092",
        consumer=False,
        producer=True,
        consumer_config=None,
        producer_config=KafkaProducerConfig(partition_key_fn=lambda _: "1"),
    )
    adapter = AIOKafkaProducerAdapter(PlayerScraped, config)
    adapter.producer = AsyncMock()

    with patch(
        "bot_detector.event_queue.adapters.kafka.adapter.AIOKafkaProducer"
    ) as mock_producer_class:
        await adapter.start()

        mock_producer_class.assert_not_called()


@pytest.mark.asyncio
async def test_producer_stop_noop_when_missing():
    config = KafkaConfig(
        topic="players",
        bootstrap_servers="localhost:9092",
        consumer=False,
        producer=True,
        consumer_config=None,
        producer_config=KafkaProducerConfig(partition_key_fn=lambda _: "1"),
    )
    adapter = AIOKafkaProducerAdapter(PlayerScraped, config)

    await adapter.stop()


@pytest.mark.asyncio
async def test_producer_send_failure():
    config = KafkaConfig(
        topic="players",
        bootstrap_servers="localhost:9092",
        consumer=False,
        producer=True,
        consumer_config=None,
        producer_config=KafkaProducerConfig(
            partition_key_fn=lambda _: "1",
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
async def test_producer_put_without_start():
    config = KafkaConfig(
        topic="players",
        bootstrap_servers="localhost:9092",
        consumer=False,
        producer=True,
        consumer_config=None,
        producer_config=KafkaProducerConfig(partition_key_fn=lambda _: "1"),
    )
    adapter = AIOKafkaProducerAdapter(PlayerScraped, config)

    result = await adapter.put([PlayerScraped(id=1, username="Alice", score=100)])

    assert isinstance(result, ProducerNotStartedError)


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
