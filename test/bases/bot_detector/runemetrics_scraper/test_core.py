import os
from unittest.mock import AsyncMock
from datetime import datetime, timedelta
import asyncio

import pytest
from bot_detector.event_queue.structs import NotFoundStruct
from bot_detector.runemetrics_api.core import RuneMetricsError, RuneMetricsResponse
from bot_detector.runemetrics_scraper import core
from bot_detector.structs import MetaData, PlayerStruct
from pydantic import BaseModel

os.environ["ENVIRONMENT"] = "test"


class DummyError(BaseModel):
    error: str
    loggedIn: bool = False


@pytest.fixture
def player_struct():
    return PlayerStruct(
        id=1,
        name="test_player",
        created_at=datetime.now() - timedelta(days=1),
        updated_at=None,
        possible_ban=False,
        confirmed_ban=False,
        confirmed_player=False,
        label_id=0,
        label_jagex=0,
        ironman=None,
        hardcore_ironman=None,
        ultimate_ironman=None,
        normalized_name=None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error_value,expected_label",
    [
        (None, 0),
        ("NO_PROFILE", 1),
        ("NOT_A_MEMBER", 2),
        ("PROFILE_PRIVATE", 3),
        ("SOMETHING_ELSE", 0),
    ],
)
async def test_update_player(player_struct: PlayerStruct, error_value, expected_label):
    runemetrics_response = RuneMetricsResponse()

    if error_value is not None:
        runemetrics_response.error = RuneMetricsError(
            error=error_value,
            loggedIn=False,
        )

    updated = await core.update_player(
        player_data=player_struct.model_copy(),
        runemetrics_response=runemetrics_response,
    )

    assert updated.label_jagex == expected_label
    assert updated.possible_ban == 1
    assert updated.confirmed_player == 0
    assert isinstance(updated.updated_at, datetime)


class _DummySession:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return None


@pytest.mark.asyncio
async def test_work_commits_offset_after_successful_handle(
    monkeypatch: pytest.MonkeyPatch,
    player_struct: PlayerStruct,
):
    player_message = NotFoundStruct(
        metadata=MetaData(version=1, source="test"),
        player_data=player_struct,
    )
    player_nf_queue = AsyncMock()
    player_nf_queue.get_one = AsyncMock(return_value=player_message)
    player_nf_queue.commit = AsyncMock(return_value=None)
    player_sc_producer = AsyncMock()
    player_sc_producer.put = AsyncMock(return_value=None)

    monkeypatch.setattr(core, "ClientSession", _DummySession)
    monkeypatch.setattr(
        core,
        "get_proxy",
        AsyncMock(side_effect=["http://user@proxy", asyncio.CancelledError()]),
    )
    monkeypatch.setattr(
        core,
        "scrape_player",
        AsyncMock(return_value=(RuneMetricsResponse(), 0.1, None)),
    )
    monkeypatch.setattr(core.asyncio, "sleep", AsyncMock(return_value=None))

    with pytest.raises(asyncio.CancelledError):
        await core.work(
            worker_id=1,
            proxy_manager=AsyncMock(),
            rate_limiter=AsyncMock(),
            player_nf_queue=player_nf_queue,
            player_sc_producer=player_sc_producer,
        )

    player_nf_queue.commit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "requeue_error,expected_commit_calls",
    [
        (None, 1),
        (Exception("requeue failed"), 0),
    ],
)
async def test_work_commits_only_after_successful_requeue(
    monkeypatch: pytest.MonkeyPatch,
    player_struct: PlayerStruct,
    requeue_error: Exception | None,
    expected_commit_calls: int,
):
    player_message = NotFoundStruct(
        metadata=MetaData(version=1, source="test"),
        player_data=player_struct,
    )
    player_nf_queue = AsyncMock()
    player_nf_queue.get_one = AsyncMock(return_value=player_message)
    player_nf_queue.put = AsyncMock(return_value=requeue_error)
    player_nf_queue.commit = AsyncMock(return_value=None)
    player_sc_producer = AsyncMock()

    monkeypatch.setattr(core, "ClientSession", _DummySession)
    monkeypatch.setattr(
        core,
        "get_proxy",
        AsyncMock(side_effect=["http://user@proxy", asyncio.CancelledError()]),
    )
    monkeypatch.setattr(
        core,
        "scrape_player",
        AsyncMock(return_value=(None, None, "temporary failure")),
    )
    monkeypatch.setattr(core.asyncio, "sleep", AsyncMock(return_value=None))

    with pytest.raises(asyncio.CancelledError):
        await core.work(
            worker_id=1,
            proxy_manager=AsyncMock(),
            rate_limiter=AsyncMock(),
            player_nf_queue=player_nf_queue,
            player_sc_producer=player_sc_producer,
        )

    assert player_nf_queue.commit.await_count == expected_commit_calls


@pytest.mark.asyncio
async def test_work_uses_backoff_sleep_on_error(
    monkeypatch: pytest.MonkeyPatch,
    player_struct: PlayerStruct,
):
    player_message = NotFoundStruct(
        metadata=MetaData(version=1, source="test"),
        player_data=player_struct,
    )
    player_nf_queue = AsyncMock()
    player_nf_queue.get_one = AsyncMock(return_value=player_message)
    player_nf_queue.put = AsyncMock(return_value=None)
    player_nf_queue.commit = AsyncMock(return_value=None)
    player_sc_producer = AsyncMock()

    monkeypatch.setattr(core, "ClientSession", _DummySession)
    monkeypatch.setattr(
        core,
        "get_proxy",
        AsyncMock(side_effect=["http://user@proxy", asyncio.CancelledError()]),
    )
    monkeypatch.setattr(
        core,
        "scrape_player",
        AsyncMock(return_value=(None, None, "temporary failure")),
    )

    sleep_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(core.asyncio, "sleep", sleep_mock)

    with pytest.raises(asyncio.CancelledError):
        await core.work(
            worker_id=1,
            proxy_manager=AsyncMock(),
            rate_limiter=AsyncMock(),
            player_nf_queue=player_nf_queue,
            player_sc_producer=player_sc_producer,
        )

    sleep_call_arg = sleep_mock.call_args[0][0]
    assert sleep_call_arg >= 1.0


@pytest.mark.asyncio
async def test_work_resets_backoff_on_success(
    monkeypatch: pytest.MonkeyPatch,
    player_struct: PlayerStruct,
):
    player_message = NotFoundStruct(
        metadata=MetaData(version=1, source="test"),
        player_data=player_struct,
    )
    player_nf_queue = AsyncMock()
    player_nf_queue.get_one = AsyncMock(return_value=player_message)
    player_nf_queue.commit = AsyncMock(return_value=None)
    player_sc_producer = AsyncMock()
    player_sc_producer.put = AsyncMock(return_value=None)

    monkeypatch.setattr(core, "ClientSession", _DummySession)
    monkeypatch.setattr(
        core,
        "get_proxy",
        AsyncMock(side_effect=["http://user@proxy", asyncio.CancelledError()]),
    )
    monkeypatch.setattr(
        core,
        "scrape_player",
        AsyncMock(return_value=(RuneMetricsResponse(), 0.1, None)),
    )

    sleep_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(core.asyncio, "sleep", sleep_mock)

    with pytest.raises(asyncio.CancelledError):
        await core.work(
            worker_id=1,
            proxy_manager=AsyncMock(),
            rate_limiter=AsyncMock(),
            player_nf_queue=player_nf_queue,
            player_sc_producer=player_sc_producer,
        )

    player_sc_producer.put.assert_awaited_once()
