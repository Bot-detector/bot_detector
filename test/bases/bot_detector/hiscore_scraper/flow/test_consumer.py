"""Unit tests for the consume stage.

The consume stage replaces the old per-player get_one + commit with
batched get_many + one commit per batch; commit-on-dequeue semantics
are unchanged (at-least-once comes from Kafka requeues, not offsets).
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from bot_detector.event_queue.structs import ToScrapeStruct
from bot_detector.hiscore_scraper.flow import consumer
from bot_detector.structs import MetaData, PlayerStruct


def _to_scrape_player(player_id: int = 1) -> ToScrapeStruct:
    player = PlayerStruct(
        id=player_id,
        name=f"player-{player_id}",
        created_at=datetime(2024, 1, 1),
    )
    return ToScrapeStruct(
        metadata=MetaData(version=1, source="test"),
        player_data=player,
    )


@pytest.mark.asyncio
async def test_consume_pushes_batch_to_task_queue_and_commits():
    batch = [_to_scrape_player(1), _to_scrape_player(2)]
    player_ts_queue = AsyncMock()
    player_ts_queue.get_many = AsyncMock(side_effect=[batch, asyncio.CancelledError()])
    player_ts_queue.commit = AsyncMock(return_value=None)
    task_queue: asyncio.Queue[ToScrapeStruct] = asyncio.Queue(maxsize=10)

    with pytest.raises(asyncio.CancelledError):
        await consumer.consume(
            player_ts_queue=player_ts_queue,
            task_queue=task_queue,
            batch_size=2,
        )

    assert task_queue.qsize() == 2
    assert task_queue.get_nowait().player_data.id == 1
    assert task_queue.get_nowait().player_data.id == 2
    # one commit per batch, not per message
    player_ts_queue.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_consume_survives_batch_error_and_retries():
    # get_many returns errors as values, so the failure is a return
    # value here, not a raised exception
    batches: list[list[ToScrapeStruct] | Exception] = [
        Exception("kafka fetch failed"),
        [_to_scrape_player(3)],
    ]

    async def _get_many(count: int) -> list[ToScrapeStruct] | Exception:
        if not batches:
            raise asyncio.CancelledError()
        return batches.pop(0)

    player_ts_queue = AsyncMock()
    player_ts_queue.get_many = _get_many
    player_ts_queue.commit = AsyncMock(return_value=None)
    task_queue: asyncio.Queue[ToScrapeStruct] = asyncio.Queue(maxsize=10)

    with pytest.raises(asyncio.CancelledError):
        await consumer.consume(
            player_ts_queue=player_ts_queue,
            task_queue=task_queue,
            batch_size=1,
        )

    # the failed batch never reached the task queue; the next one did
    assert task_queue.qsize() == 1
    assert task_queue.get_nowait().player_data.id == 3


@pytest.mark.asyncio
async def test_consume_continues_after_commit_error():
    player_ts_queue = AsyncMock()
    player_ts_queue.get_many = AsyncMock(
        side_effect=[[_to_scrape_player(4)], asyncio.CancelledError()]
    )
    player_ts_queue.commit = AsyncMock(return_value=Exception("commit failed"))
    task_queue: asyncio.Queue[ToScrapeStruct] = asyncio.Queue(maxsize=10)

    with pytest.raises(asyncio.CancelledError):
        await consumer.consume(
            player_ts_queue=player_ts_queue,
            task_queue=task_queue,
            batch_size=1,
        )

    # the batch was handed out despite the failed commit: redelivery
    # may duplicate these players, which the requeue contract tolerates
    assert task_queue.qsize() == 1
