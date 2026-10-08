from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bot_detector.event_queue.structs import PredictionsToInsertStruct
from bot_detector.worker_prediction.worker import PredictionWorker, insert_batch


def _build_prediction(player_id: int = 123) -> PredictionsToInsertStruct:
    return PredictionsToInsertStruct(
        model_name="multi_model_v1",
        player_id=player_id,
        prediction="Real_Player",
        confidence=0.9,
        predictions={"Real_Player": 0.9},
    )


def _mock_session_factory() -> MagicMock:
    session = AsyncMock()
    session_factory = MagicMock()
    session_factory.return_value.__aenter__ = AsyncMock(return_value=session)
    session_factory.return_value.__aexit__ = AsyncMock(return_value=None)
    return session_factory


@pytest.mark.asyncio
async def test_insert_batch_calls_both_repos():
    batch = [_build_prediction(), _build_prediction(player_id=456)]
    prediction_repo = AsyncMock()
    prediction_latest_repo = AsyncMock()

    await insert_batch(
        prediction_repo=prediction_repo,
        prediction_latest_repo=prediction_latest_repo,
        batch=batch,
        session_factory=_mock_session_factory(),
    )

    prediction_repo.insert.assert_awaited_once()
    prediction_latest_repo.insert.assert_awaited_once()
    assert prediction_repo.insert.await_args.kwargs["predictions"] == batch
    assert prediction_latest_repo.insert.await_args.kwargs["predictions"] == batch


@pytest.mark.asyncio
async def test_handle_calls_insert_batch():
    batch = [_build_prediction()]
    prediction_repo = AsyncMock()
    prediction_latest_repo = AsyncMock()

    w = PredictionWorker(
        worker_id=0,
        session_factory=MagicMock(),
        prediction_repo=prediction_repo,
        prediction_latest_repo=prediction_latest_repo,
    )

    with patch(
        "bot_detector.worker_prediction.worker.insert_batch", new_callable=AsyncMock
    ) as mock_insert:
        result = await w.handle(batch)

    mock_insert.assert_awaited_once()
    assert result == []
    prediction_repo.insert.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_empty_batch_is_noop():
    prediction_repo = AsyncMock()
    prediction_latest_repo = AsyncMock()

    w = PredictionWorker(
        worker_id=0,
        session_factory=MagicMock(),
        prediction_repo=prediction_repo,
        prediction_latest_repo=prediction_latest_repo,
    )

    result = await w.handle([])

    assert result == []
    prediction_repo.insert.assert_not_awaited()
    prediction_latest_repo.insert.assert_not_awaited()
