from unittest.mock import AsyncMock

import pytest
from bot_detector.kafka.data_to_predict import (
    DataToPredictProducer,
    DataToPredictStruct,
)


@pytest.fixture
def fake_producer():
    """Fixture to create a fake Kafka producer."""
    mock_producer = AsyncMock()
    return mock_producer


@pytest.mark.asyncio
async def test_produce_one_simple(fake_producer):
    producer = DataToPredictProducer("localhost:9092")
    producer._producer = fake_producer

    test_data = DataToPredictStruct.model_validate(
        {
            "player_id": 123,
            "data": {},
        }
    )

    await producer.produce_one(test_data)

    fake_producer.send.assert_called_once()
