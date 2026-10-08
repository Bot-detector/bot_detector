from unittest.mock import AsyncMock, MagicMock

import pytest
from bot_detector.event_queue.structs import PredictionsToInsertStruct
from bot_detector.worker_prediction.worker import insert_batch
from prometheus_client import REGISTRY


def _build_prediction(player_id: int = 123) -> PredictionsToInsertStruct:
    return PredictionsToInsertStruct(
        model_name="multi_model_v1",
        player_id=player_id,
        prediction="Real_Player",
        confidence=0.9,
        predictions={"Real_Player": 0.9},
    )


def _sample(name: str) -> float | None:
    return REGISTRY.get_sample_value(name)


def _mock_session_factory() -> MagicMock:
    session = AsyncMock()
    session_factory = MagicMock()
    session_factory.return_value.__aenter__ = AsyncMock(return_value=session)
    session_factory.return_value.__aexit__ = AsyncMock(return_value=None)
    return session_factory


@pytest.mark.asyncio
async def test_insert_batch_increments_inserted_counter():
    batch = [_build_prediction(), _build_prediction(player_id=456)]
    before = _sample("worker_prediction_predictions_inserted_total") or 0

    await insert_batch(
        prediction_repo=AsyncMock(),
        prediction_latest_repo=AsyncMock(),
        batch=batch,
        session_factory=_mock_session_factory(),
    )

    assert (_sample("worker_prediction_predictions_inserted_total") or 0) == before + 2
