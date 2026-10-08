import os
from unittest.mock import AsyncMock

import pytest

os.environ.setdefault("BASE_URL", "http://localhost")
os.environ.setdefault("MODEL_NAME", "dummy")

from bot_detector.event_queue.structs import DataToPredictStruct
from bot_detector.ml_api import Prediction
from bot_detector.worker_ml import core
from prometheus_client import REGISTRY


class _StopLoop(BaseException):
    pass


def _sample(name: str, labels: dict[str, str] | None = None) -> float | None:
    return REGISTRY.get_sample_value(name, labels)


def _prediction() -> Prediction:
    data = {
        name: 0.9 if name == "Real_Player" else 0.005
        for name in Prediction.model_fields
    }
    return Prediction.model_validate(data)


@pytest.mark.asyncio
async def test_consume_data_to_predict_increments_prediction_counters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    batch = [DataToPredictStruct(player_id=123, data={"attack": 1})]
    published_before = _sample("worker_ml_predictions_published_total") or 0
    batches_before = (
        _sample("worker_ml_batches_consumed_total", {"loop": "data_to_predict"}) or 0
    )

    queue = AsyncMock()
    queue.get_many = AsyncMock(side_effect=[batch, []])
    queue.commit = AsyncMock()

    predictions_queue = AsyncMock()

    monkeypatch_predict = AsyncMock(return_value=[_prediction()])
    monkeypatch.setattr(core, "predict", monkeypatch_predict)
    monkeypatch.setattr(core.asyncio, "sleep", AsyncMock(side_effect=_StopLoop()))

    with pytest.raises(_StopLoop):
        await core.consume_data_to_predict(
            max_messages=10,
            data_to_predict_queue=queue,
            api=AsyncMock(),
            predictions_queue=predictions_queue,
        )

    assert monkeypatch_predict.await_count == 1
    assert queue.commit.await_count == 1
    assert (
        _sample("worker_ml_predictions_published_total") or 0
    ) == published_before + 1
    assert (
        _sample("worker_ml_batches_consumed_total", {"loop": "data_to_predict"}) or 0
    ) == batches_before + 1
