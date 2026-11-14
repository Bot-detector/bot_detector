from unittest.mock import AsyncMock, patch

import pytest
from aiokafka.errors import KafkaError
from bot_detector.event_queue.adapters.kafka import (
    AIOKafkaConsumerAdapter,
    KafkaConfig,
    KafkaConsumerConfig,
)
from bot_detector.event_queue.core.errors import (
    ConsumerConfigError,
    ConsumerFetchError,
    ConsumerNotStartedError,
    MessageTypeError,
)
from prometheus_client import REGISTRY
from pydantic import BaseModel, ValidationError


def _skipped_total() -> float | None:
    return REGISTRY.get_sample_value("event_queue_messages_skipped_total")


class PlayerScraped(BaseModel):
    id: int
    username: str
    score: int


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
async def test_consumer_get_one_validation_error():
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
    fake_record.value = {"id": 1}

    adapter.consumer = AsyncMock()
    adapter.consumer.getone = AsyncMock(return_value=fake_record)

    result = await adapter.get_one()

    assert isinstance(result, ValidationError)


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
async def test_consumer_start_noop_when_existing():
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

    with patch(
        "bot_detector.event_queue.adapters.kafka.adapter.AIOKafkaConsumer"
    ) as mock_consumer_class:
        await adapter.start()

        mock_consumer_class.assert_not_called()


@pytest.mark.asyncio
async def test_consumer_stop_noop_when_missing():
    config = KafkaConfig(
        topic="players",
        bootstrap_servers="localhost:9092",
        consumer=True,
        producer=False,
        consumer_config=KafkaConsumerConfig(group_id="group"),
        producer_config=None,
    )
    adapter = AIOKafkaConsumerAdapter(PlayerScraped, config)

    await adapter.stop()


@pytest.mark.asyncio
async def test_consumer_get_many_without_start():
    config = KafkaConfig(
        topic="players",
        bootstrap_servers="localhost:9092",
        consumer=True,
        producer=False,
        consumer_config=KafkaConsumerConfig(group_id="group"),
        producer_config=None,
    )
    adapter = AIOKafkaConsumerAdapter(PlayerScraped, config)

    result = await adapter.get_many(1)

    assert isinstance(result, ConsumerNotStartedError)


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
async def test_consumer_get_many_timeout_break():
    class FakeBatcher:
        def __class_getitem__(cls, item: object) -> "FakeBatcher":
            return cls

        def __init__(self, batch_size: int, timeout_ms: int) -> None:
            self.batch_size = batch_size
            self.timeout_ms = timeout_ms
            self.size = 0
            self.time_left = 0.0

        def check_flush(self) -> bool:
            return False

        def append(self, event: PlayerScraped, auto: bool = True) -> None:
            return None

        def flush(self) -> list[PlayerScraped]:
            return []

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

    with patch(
        "bot_detector.event_queue.adapters.kafka.adapter.Batcher",
        FakeBatcher,
    ):
        result = await adapter.get_many(1)

    assert result == []


@pytest.mark.asyncio
async def test_consumer_get_many_empty_records_sleeps():
    class FakeBatcher:
        def __class_getitem__(cls, item: object) -> "FakeBatcher":
            return cls

        def __init__(self, batch_size: int, timeout_ms: int) -> None:
            self.batch_size = batch_size
            self.timeout_ms = timeout_ms
            self.size = 0
            self.time_left = 1.0
            self._checks = iter([False, True])

        def check_flush(self) -> bool:
            return next(self._checks)

        def append(self, event: PlayerScraped, auto: bool = True) -> None:
            return None

        def flush(self) -> list[PlayerScraped]:
            return []

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
    adapter.consumer.getmany = AsyncMock(return_value={})

    with (
        patch(
            "bot_detector.event_queue.adapters.kafka.adapter.Batcher",
            FakeBatcher,
        ),
        patch(
            "bot_detector.event_queue.adapters.kafka.adapter.asyncio.sleep",
            new=AsyncMock(),
        ) as sleep_mock,
    ):
        result = await adapter.get_many(1)

    assert result == []
    sleep_mock.assert_awaited_once()


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
    adapter.consumer.getone = AsyncMock(side_effect=KafkaError("boom"))

    result = await adapter.get_one()
    assert isinstance(result, ConsumerFetchError)
    assert isinstance(result.cause, Exception)


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
    adapter.consumer.getmany = AsyncMock(side_effect=KafkaError("boom"))

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
        # short timeout: a page of all-invalid records keeps the loop
        # polling until the batcher's timer ends it
        consumer_config=KafkaConsumerConfig(group_id="group", consume_timeout_ms=100),
        producer_config=None,
    )
    adapter = AIOKafkaConsumerAdapter(PlayerScraped, config)

    fake_record = AsyncMock()
    fake_record.value = "not-a-dict"

    adapter.consumer = AsyncMock()
    adapter.consumer.getmany = AsyncMock(return_value={0: [fake_record]})

    # invalid records are skipped loudly (counter + log), not returned:
    # returning would discard the batch and stall the partition forever
    before = _skipped_total()
    result = await adapter.get_many(1)

    assert result == []
    assert _skipped_total() is not None
    assert (_skipped_total() or 0) >= (before or 0) + 1


@pytest.mark.asyncio
async def test_consumer_get_many_skips_poison_keeps_valid():
    config = KafkaConfig(
        topic="players",
        bootstrap_servers="localhost:9092",
        consumer=True,
        producer=False,
        consumer_config=KafkaConsumerConfig(group_id="group"),
        producer_config=None,
    )
    adapter = AIOKafkaConsumerAdapter(PlayerScraped, config)

    poison_record = AsyncMock()
    poison_record.value = {"_poison": True, "raw": "garbage"}
    valid_record = AsyncMock()
    valid_record.value = {"id": 1, "username": "Alice", "score": 100}

    adapter.consumer = AsyncMock()
    adapter.consumer.getmany = AsyncMock(
        return_value={0: [poison_record, valid_record]}
    )

    # one page of 2 records against a requested count of 1: the overshoot
    # fills the batcher immediately, so the loop ends after one call
    before = _skipped_total()
    result = await adapter.get_many(1)

    assert not isinstance(result, Exception)
    assert [item.username for item in result] == ["Alice"]
    assert _skipped_total() == (before or 0) + 1


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


@pytest.mark.asyncio
async def test_consumer_commit_success():
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
    adapter.consumer.commit = AsyncMock(return_value=None)

    result = await adapter.commit()

    adapter.consumer.commit.assert_awaited_once()
    assert result is None


@pytest.mark.asyncio
async def test_consumer_commit_propagates_error_value():
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
    commit_error = Exception("commit failed")
    adapter.consumer.commit = AsyncMock(return_value=commit_error)

    result = await adapter.commit()

    assert result is commit_error
