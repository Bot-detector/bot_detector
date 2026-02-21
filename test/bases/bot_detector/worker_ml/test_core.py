import os
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock

import pytest

os.environ.setdefault("BASE_URL", "http://localhost")
os.environ.setdefault("MODEL_NAME", "dummy")

from bot_detector.event_queue.structs import DataToPredictStruct, ScrapedStruct
from bot_detector.structs import HighscoreBaseStruct, MetaData, PlayerStruct
from bot_detector.worker_ml import core


class _StopLoop(BaseException):
    pass


@pytest.fixture
def data_to_predict_batch() -> list[DataToPredictStruct]:
    return [
        DataToPredictStruct(
            player_id=123,
            data={"attack": 1},
        )
    ]


@pytest.fixture
def scraped_batch() -> list[ScrapedStruct]:
    return [
        ScrapedStruct(
            metadata=MetaData(version=1, source="test"),
            player_data=PlayerStruct(
                id=123,
                name="tester",
                created_at=datetime.now(tz=UTC),
            ),
            highscore_data=HighscoreBaseStruct(
                player_id=123,
                scrape_date=date.today(),
                time_to_live=date.today(),
                skills={"attack": 10},
                activities={},
            ),
        )
    ]


def test_sample():
    assert core is not None


@pytest.mark.asyncio
async def test_consume_data_to_predict_does_not_commit_when_requeue_fails_after_predict_error(
    monkeypatch: pytest.MonkeyPatch,
    data_to_predict_batch: list[DataToPredictStruct],
) -> None:
    queue = AsyncMock()
    queue.get_many = AsyncMock(return_value=data_to_predict_batch)
    queue.put = AsyncMock(return_value=Exception("requeue failed"))
    queue.commit = AsyncMock()

    monkeypatch.setattr(core, "predict", AsyncMock(side_effect=Exception("ml failed")))
    monkeypatch.setattr(core.asyncio, "sleep", AsyncMock(side_effect=_StopLoop()))

    with pytest.raises(_StopLoop):
        await core.consume_data_to_predict(
            max_messages=10,
            data_to_predict_queue=queue,
            api=AsyncMock(),
            session_factory=AsyncMock(),
        )

    queue.put.assert_awaited_once_with(data_to_predict_batch)
    queue.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_consume_data_to_predict_does_not_commit_when_requeue_fails_after_db_error(
    monkeypatch: pytest.MonkeyPatch,
    data_to_predict_batch: list[DataToPredictStruct],
) -> None:
    queue = AsyncMock()
    queue.get_many = AsyncMock(return_value=data_to_predict_batch)
    queue.put = AsyncMock(return_value=Exception("requeue failed"))
    queue.commit = AsyncMock()

    monkeypatch.setattr(
        core,
        "predict",
        AsyncMock(return_value=[AsyncMock(model_dump=lambda: {"bot": 1.0})]),
    )
    monkeypatch.setattr(
        core,
        "insert_prediction_results",
        AsyncMock(side_effect=Exception("db failed")),
    )
    monkeypatch.setattr(core.asyncio, "sleep", AsyncMock(side_effect=_StopLoop()))

    with pytest.raises(_StopLoop):
        await core.consume_data_to_predict(
            max_messages=10,
            data_to_predict_queue=queue,
            api=AsyncMock(),
            session_factory=AsyncMock(),
        )

    queue.put.assert_awaited_once_with(data_to_predict_batch)
    queue.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_consume_player_scraped_does_not_commit_when_requeue_fails_after_predict_error(
    monkeypatch: pytest.MonkeyPatch,
    scraped_batch: list[ScrapedStruct],
) -> None:
    queue = AsyncMock()
    queue.get_many = AsyncMock(return_value=scraped_batch)
    queue.put = AsyncMock(return_value=Exception("requeue failed"))
    queue.commit = AsyncMock()

    monkeypatch.setattr(core, "predict", AsyncMock(side_effect=Exception("ml failed")))
    monkeypatch.setattr(core.asyncio, "sleep", AsyncMock(side_effect=_StopLoop()))

    with pytest.raises(_StopLoop):
        await core.consume_player_scraped(
            max_messages=10,
            player_sc_queue=queue,
            api=AsyncMock(),
            session_factory=AsyncMock(),
        )

    queue.put.assert_awaited_once_with(scraped_batch)
    queue.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_consume_player_scraped_does_not_commit_when_requeue_fails_in_outer_handler(
    monkeypatch: pytest.MonkeyPatch,
    scraped_batch: list[ScrapedStruct],
) -> None:
    queue = AsyncMock()
    queue.get_many = AsyncMock(return_value=scraped_batch)
    queue.put = AsyncMock(return_value=Exception("requeue failed"))
    queue.commit = AsyncMock()

    monkeypatch.setattr(
        core,
        "predict",
        AsyncMock(return_value=[AsyncMock(model_dump=lambda: {"bot": 1.0})]),
    )
    monkeypatch.setattr(
        core,
        "insert_prediction_results",
        AsyncMock(side_effect=Exception("db failed")),
    )
    monkeypatch.setattr(core.asyncio, "sleep", AsyncMock(side_effect=_StopLoop()))

    with pytest.raises(_StopLoop):
        await core.consume_player_scraped(
            max_messages=10,
            player_sc_queue=queue,
            api=AsyncMock(),
            session_factory=AsyncMock(),
        )

    queue.put.assert_awaited_once_with(scraped_batch)
    queue.commit.assert_not_awaited()
