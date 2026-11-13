"""Unit tests for produce_with_retry.

The retry contract: put until success, exponential backoff between
attempts, None on success, the last error wrapped in an Exception on
exhaustion.
"""

from unittest.mock import AsyncMock

import pytest
from bot_detector.hiscore_scraper.player_outcomes.service import produce_with_retry


def _producer(put_results: list[Exception | None]) -> AsyncMock:
    producer = AsyncMock()
    results = iter(put_results)

    async def put(_messages):
        # side_effect lists raise Exception items instead of returning
        # them; a callable side effect returns them as values
        return next(results)

    producer.put = AsyncMock(side_effect=put)
    return producer


@pytest.mark.asyncio
async def test_returns_none_on_first_success():
    producer = _producer([None])

    error = await produce_with_retry(producer, lambda: object(), label="test")

    assert error is None
    producer.put.assert_awaited_once()


@pytest.mark.asyncio
async def test_retries_until_success():
    producer = _producer([Exception("kafka down"), None])

    error = await produce_with_retry(producer, lambda: object(), label="test")

    assert error is None
    assert producer.put.await_count == 2


@pytest.mark.asyncio
async def test_exhaustion_wraps_last_error():
    producer = _producer([Exception("kafka down")] * 3)

    error = await produce_with_retry(producer, lambda: object(), label="test")

    assert isinstance(error, Exception)
    assert "after 3 attempts" in str(error)
    assert "kafka down" in str(error)
    assert producer.put.await_count == 3


@pytest.mark.asyncio
async def test_custom_max_retries():
    producer = _producer([Exception("kafka down")] * 5)

    error = await produce_with_retry(
        producer, lambda: object(), label="test", max_retries=5
    )

    assert isinstance(error, Exception)
    assert producer.put.await_count == 5


@pytest.mark.asyncio
async def test_builds_message_each_attempt():
    builds: list[object] = []

    def build() -> object:
        message = object()
        builds.append(message)
        return message

    producer = _producer([Exception("kafka down"), None])
    await produce_with_retry(producer, build, label="test")

    assert len(builds) == 2
    # each attempt produces a freshly built message
    assert builds[0] is not builds[1]
