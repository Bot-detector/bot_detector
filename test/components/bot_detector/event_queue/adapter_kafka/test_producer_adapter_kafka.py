from datetime import datetime
from typing import Optional
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
from bot_detector.event_queue.structs import ToScrapeStruct
from bot_detector.structs import MetaData, PlayerStruct
from pydantic import BaseModel


class PlayerScraped(BaseModel):
    id: int
    username: str
    score: int


class PlayerWithNulls(BaseModel):
    id: int
    username: Optional[str] = None
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


@pytest.mark.asyncio
async def test_producer_exclude_none_drops_null_fields():
    config = KafkaConfig(
        topic="players",
        bootstrap_servers="localhost:9092",
        consumer=False,
        producer=True,
        consumer_config=None,
        producer_config=KafkaProducerConfig(exclude_none=True),
    )
    adapter = AIOKafkaProducerAdapter(PlayerWithNulls, config)
    adapter.producer = AsyncMock()
    adapter.producer.send = AsyncMock()

    await adapter.put([PlayerWithNulls(id=1, username=None, score=100)])

    adapter.producer.send.assert_called_once_with(
        topic="players",
        value={"id": 1, "score": 100},
        key=None,
    )


@pytest.mark.asyncio
async def test_producer_exclude_none_keeps_set_fields():
    config = KafkaConfig(
        topic="players",
        bootstrap_servers="localhost:9092",
        consumer=False,
        producer=True,
        consumer_config=None,
        producer_config=KafkaProducerConfig(exclude_none=True),
    )
    adapter = AIOKafkaProducerAdapter(PlayerWithNulls, config)
    adapter.producer = AsyncMock()
    adapter.producer.send = AsyncMock()

    await adapter.put([PlayerWithNulls(id=1, username="Alice", score=100)])

    adapter.producer.send.assert_called_once_with(
        topic="players",
        value={"id": 1, "username": "Alice", "score": 100},
        key=None,
    )


@pytest.mark.asyncio
async def test_producer_default_keeps_null_fields():
    config = KafkaConfig(
        topic="players",
        bootstrap_servers="localhost:9092",
        consumer=False,
        producer=True,
        consumer_config=None,
        producer_config=KafkaProducerConfig(),
    )
    adapter = AIOKafkaProducerAdapter(PlayerWithNulls, config)
    adapter.producer = AsyncMock()
    adapter.producer.send = AsyncMock()

    await adapter.put([PlayerWithNulls(id=1, username=None, score=100)])

    adapter.producer.send.assert_called_once_with(
        topic="players",
        value={"id": 1, "username": None, "score": 100},
        key=None,
    )


def _to_scrape_player(player_id: int, **optionals) -> ToScrapeStruct:
    player = PlayerStruct(
        id=player_id,
        name=f"player-{player_id}",
        created_at=datetime(2024, 1, 1),
        **optionals,
    )
    return ToScrapeStruct(
        metadata=MetaData(version=1, source="test"),
        player_data=player,
    )


def test_to_scrape_slim_payload_round_trips_to_full_struct():
    """Exclude-none serialization must not change the rehydrated struct.

    Producers drop the always-null PlayerStruct optionals
    (ironman, hardcore_ironman, ultimate_ironman, normalized_name)
    from players.to_scrape payloads; consumers validate with the same
    pydantic model, whose Optionals default back to None.
    """
    full = _to_scrape_player(
        9,
        ironman=None,
        hardcore_ironman=None,
        ultimate_ironman=None,
        normalized_name=None,
    )

    slim_bytes = orjson.dumps(full.model_dump(exclude_none=True))

    # the slim payload really omits the null-valued keys
    dumped = orjson.loads(slim_bytes)
    slim_player = dumped["player_data"]
    assert "ironman" not in slim_player
    assert "hardcore_ironman" not in slim_player
    assert "ultimate_ironman" not in slim_player
    assert "normalized_name" not in slim_player

    rehydrated = ToScrapeStruct.model_validate(dumped)
    # slim bytes and full bytes rehydrate to the same struct
    assert rehydrated == ToScrapeStruct.model_validate(full.model_dump())
    assert rehydrated.player_data == full.player_data


def test_to_scrape_slim_payload_keeps_set_optional_fields():
    """exclude_none drops nulls only: set optionals must survive."""
    full = _to_scrape_player(10, ironman=True)

    slim_bytes = orjson.dumps(full.model_dump(exclude_none=True))

    rehydrated = ToScrapeStruct.model_validate(orjson.loads(slim_bytes))

    assert rehydrated.player_data.ironman is True
    assert rehydrated == full
