import pytest

from bases.api_public.feedback.schemas import FeedbackInput


def _base_feedback_kwargs() -> dict:
    return {
        "player_name": "Some_Player",
        "vote": 1,
        "prediction": "bot",
        "confidence": 0.5,
        "subject_id": 123,
    }


def test_feedback_input_accepts_valid_osrs_name():
    data = FeedbackInput(**_base_feedback_kwargs())
    assert data.player_name == "Some_Player"


def test_feedback_input_rejects_invalid_name():
    bad_kwargs = _base_feedback_kwargs()
    bad_kwargs["player_name"] = "this-name-is-way-too-long"
    with pytest.raises(ValueError):
        FeedbackInput(**bad_kwargs)
