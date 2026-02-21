import asyncio
from datetime import date, datetime
from unittest.mock import AsyncMock

import pytest

from bot_detector.event_queue.structs import ScrapedStruct
from bot_detector.structs._metadata import MetaData
from bot_detector.structs.hiscore import HighscoreBaseStruct
from bot_detector.structs.player import PlayerStruct
from bot_detector.worker_hiscore import core


def _build_scraped_struct() -> ScrapedStruct:
    return ScrapedStruct(
        metadata=MetaData(version=1, source="test"),
        player_data=PlayerStruct(
            id=1,
            name="tester",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        ),
        highscore_data=HighscoreBaseStruct(
            player_id=1,
            scrape_date=date.today(),
            time_to_live=date.today(),
            skills={"attack": 99},
            activities={"league_points": 1},
        ),
    )


@pytest.mark.asyncio
async def test_consume_many_task_skips_commit_when_requeue_fails(
    monkeypatch: pytest.MonkeyPatch,
):
    batch = [_build_scraped_struct(), _build_scraped_struct()]
    player_sc_queue = AsyncMock()
    player_sc_queue.get_many = AsyncMock(return_value=batch)
    player_sc_queue.put = AsyncMock(return_value=Exception("requeue-failed"))
    player_sc_queue.commit = AsyncMock(return_value=None)

    async def _fake_insert_batch(**_kwargs):
        return None, "insert-failed"

    async def _fake_produce_data_to_predict(**_kwargs):
        return None

    async def _cancel_sleep(_seconds: int):
        raise asyncio.CancelledError()

    monkeypatch.setattr(core, "insert_batch", _fake_insert_batch)
    monkeypatch.setattr(core, "produce_data_to_predict", _fake_produce_data_to_predict)
    monkeypatch.setattr(core.asyncio, "sleep", _cancel_sleep)

    with pytest.raises(asyncio.CancelledError):
        await core.consume_many_task(
            worker_id=1,
            max_messages=10,
            player_sc_queue=player_sc_queue,
            data_to_predict_producer=AsyncMock(),
            highscore_repo=AsyncMock(),
            player_repo=AsyncMock(),
            session_factory=AsyncMock(),
        )

    player_sc_queue.commit.assert_not_awaited()
    player_sc_queue.put.assert_awaited_once_with(batch)


@pytest.mark.asyncio
async def test_consume_many_task_commits_when_requeue_succeeds(
    monkeypatch: pytest.MonkeyPatch,
):
    batch = [_build_scraped_struct(), _build_scraped_struct()]
    player_sc_queue = AsyncMock()
    player_sc_queue.get_many = AsyncMock(return_value=batch)
    player_sc_queue.put = AsyncMock(return_value=None)
    player_sc_queue.commit = AsyncMock(return_value=None)

    async def _fake_insert_batch(**_kwargs):
        return None, "insert-failed"

    async def _fake_produce_data_to_predict(**_kwargs):
        return None

    async def _cancel_sleep(_seconds: int):
        raise asyncio.CancelledError()

    monkeypatch.setattr(core, "insert_batch", _fake_insert_batch)
    monkeypatch.setattr(core, "produce_data_to_predict", _fake_produce_data_to_predict)
    monkeypatch.setattr(core.asyncio, "sleep", _cancel_sleep)

    with pytest.raises(asyncio.CancelledError):
        await core.consume_many_task(
            worker_id=1,
            max_messages=10,
            player_sc_queue=player_sc_queue,
            data_to_predict_producer=AsyncMock(),
            highscore_repo=AsyncMock(),
            player_repo=AsyncMock(),
            session_factory=AsyncMock(),
        )

    player_sc_queue.commit.assert_awaited_once()
    player_sc_queue.put.assert_awaited_once_with(batch)
