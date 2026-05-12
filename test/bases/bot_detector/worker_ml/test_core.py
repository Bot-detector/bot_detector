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
async def test_data_to_predict_worker_raises_on_predict_error(
    monkeypatch: pytest.MonkeyPatch,
    data_to_predict_batch: list[DataToPredictStruct],
) -> None:
    monkeypatch.setattr(core, "predict", AsyncMock(side_effect=Exception("ml failed")))

    worker = core.DataToPredictWorker(
        api=AsyncMock(),
        model_name="test_model",
        session_factory=AsyncMock(),
    )

    with pytest.raises(Exception, match="ml failed"):
        await worker.handle(data_to_predict_batch)


@pytest.mark.asyncio
async def test_data_to_predict_worker_raises_on_db_error(
    monkeypatch: pytest.MonkeyPatch,
    data_to_predict_batch: list[DataToPredictStruct],
) -> None:
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

    worker = core.DataToPredictWorker(
        api=AsyncMock(),
        model_name="test_model",
        session_factory=AsyncMock(),
    )

    with pytest.raises(Exception, match="db failed"):
        await worker.handle(data_to_predict_batch)


@pytest.mark.asyncio
async def test_player_scraped_worker_raises_on_predict_error(
    monkeypatch: pytest.MonkeyPatch,
    scraped_batch: list[ScrapedStruct],
) -> None:
    monkeypatch.setattr(core, "predict", AsyncMock(side_effect=Exception("ml failed")))

    worker = core.PlayerScrapedWorker(
        api=AsyncMock(),
        model_name="test_model",
        session_factory=AsyncMock(),
    )

    with pytest.raises(Exception, match="ml failed"):
        await worker.handle(scraped_batch)


@pytest.mark.asyncio
async def test_player_scraped_worker_raises_on_db_error(
    monkeypatch: pytest.MonkeyPatch,
    scraped_batch: list[ScrapedStruct],
) -> None:
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

    worker = core.PlayerScrapedWorker(
        api=AsyncMock(),
        model_name="test_model",
        session_factory=AsyncMock(),
    )

    with pytest.raises(Exception, match="db failed"):
        await worker.handle(scraped_batch)
