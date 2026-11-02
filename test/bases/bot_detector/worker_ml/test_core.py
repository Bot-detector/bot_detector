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


def test_transform_scraped_struct_maps_jagex_activity_names(
    scraped_batch: list[ScrapedStruct],
) -> None:
    scraped = scraped_batch[0].model_copy(deep=True)
    scraped.highscore_data.skills = {"Runecraft": 5_000_000}  # type: ignore[union-attr]
    scraped.highscore_data.activities = {  # type: ignore[union-attr]
        "Abyssal Sire": 1200,
        "LMS - Rank": 2500,
        "Soul Wars Zeal": 9000,
    }

    player, input_data = core.transform_scraped_struct(scraped)

    assert player is scraped
    assert input_data.runecraft == 5_000_000
    assert input_data.abyssal_sire == 1200
    assert input_data.lms_rank == 2500
    assert input_data.soul_wars_zeal == 9000


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
            predictions_queue=AsyncMock(),
        )

    queue.put.assert_awaited_once_with(data_to_predict_batch)
    queue.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_consume_data_to_predict_does_not_commit_when_requeue_fails_after_publish_error(
    monkeypatch: pytest.MonkeyPatch,
    data_to_predict_batch: list[DataToPredictStruct],
) -> None:
    queue = AsyncMock()
    queue.get_many = AsyncMock(return_value=data_to_predict_batch)
    queue.put = AsyncMock(return_value=Exception("requeue failed"))
    queue.commit = AsyncMock()

    predictions_queue = AsyncMock()
    predictions_queue.put = AsyncMock(return_value=Exception("publish failed"))

    monkeypatch.setattr(
        core,
        "predict",
        AsyncMock(return_value=[AsyncMock(model_dump=lambda: {"bot": 1.0})]),
    )
    monkeypatch.setattr(core.asyncio, "sleep", AsyncMock(side_effect=_StopLoop()))

    with pytest.raises(_StopLoop):
        await core.consume_data_to_predict(
            max_messages=10,
            data_to_predict_queue=queue,
            api=AsyncMock(),
            predictions_queue=predictions_queue,
        )

    queue.put.assert_awaited_once_with(data_to_predict_batch)
    queue.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_consume_data_to_predict_commits_after_publish(
    monkeypatch: pytest.MonkeyPatch,
    data_to_predict_batch: list[DataToPredictStruct],
) -> None:
    queue = AsyncMock()
    queue.get_many = AsyncMock(side_effect=[data_to_predict_batch, []])
    queue.commit = AsyncMock()

    predictions_queue = AsyncMock()

    monkeypatch.setattr(
        core,
        "predict",
        AsyncMock(return_value=[AsyncMock(model_dump=lambda: {"bot": 1.0})]),
    )
    monkeypatch.setattr(core.asyncio, "sleep", AsyncMock(side_effect=_StopLoop()))

    with pytest.raises(_StopLoop):
        await core.consume_data_to_predict(
            max_messages=10,
            data_to_predict_queue=queue,
            api=AsyncMock(),
            predictions_queue=predictions_queue,
        )

    predictions_queue.put.assert_awaited_once()
    queue.commit.assert_awaited_once()


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
            predictions_queue=AsyncMock(),
        )

    queue.put.assert_awaited_once_with(scraped_batch)
    queue.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_consume_player_scraped_does_not_commit_when_requeue_fails_after_publish_error(
    monkeypatch: pytest.MonkeyPatch,
    scraped_batch: list[ScrapedStruct],
) -> None:
    queue = AsyncMock()
    queue.get_many = AsyncMock(return_value=scraped_batch)
    queue.put = AsyncMock(return_value=Exception("requeue failed"))
    queue.commit = AsyncMock()

    predictions_queue = AsyncMock()
    predictions_queue.put = AsyncMock(return_value=Exception("publish failed"))

    monkeypatch.setattr(
        core,
        "predict",
        AsyncMock(return_value=[AsyncMock(model_dump=lambda: {"bot": 1.0})]),
    )
    monkeypatch.setattr(core.asyncio, "sleep", AsyncMock(side_effect=_StopLoop()))

    with pytest.raises(_StopLoop):
        await core.consume_player_scraped(
            max_messages=10,
            player_sc_queue=queue,
            api=AsyncMock(),
            predictions_queue=predictions_queue,
        )

    queue.put.assert_awaited_once_with(scraped_batch)
    queue.commit.assert_not_awaited()
