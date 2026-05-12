import logging
from typing import Any

from bot_detector.event_queue.structs import (
    DataToPredictStruct,
    HighScoreStruct,
    ScrapedStruct,
)
from pydantic import ValidationError

logger = logging.getLogger(__name__)


def clean_dict(data: dict[str, Any]) -> dict:
    """
    Recursively remove keys with None values from a dictionary.
    """
    assert isinstance(data, dict), "Input must be a dictionary"
    return {k.lower(): v for k, v in data.items() if v is not None}


def transform_highscore_struct(
    record: ScrapedStruct, player_id: int
) -> HighScoreStruct | None:
    assert record.highscore_data is not None, "Highscore data must not be None"
    skills = clean_dict(record.highscore_data.skills or {})
    activities = clean_dict(record.highscore_data.activities or {})

    try:
        _data = HighScoreStruct.model_validate(skills | activities)
        return _data
    except ValidationError as e:
        logger.error(
            "Failed to validate HighScoreStruct",
            extra={
                "player_id": player_id,
                "data": skills | activities,
                "errors": e.errors(),
            },
            exc_info=True,
        )
    return None


def transform_data_to_predict_struct(
    player_id: int, hs_struct: HighScoreStruct | None
) -> DataToPredictStruct | None:
    try:
        data = {
            "player_id": player_id,
            "data": hs_struct,
        }
        return DataToPredictStruct.model_validate(data)
    except ValidationError as e:
        logger.error(
            "Failed to validate DataToPredictStruct",
            extra={
                "player_id": player_id,
                "data": hs_struct,
                "errors": e.errors(),
            },
            exc_info=True,
        )
        return None


def transform_scraped_struct(
    record: ScrapedStruct,
) -> DataToPredictStruct | None:
    if record.highscore_data is None:
        logger.debug("Highscore data is None")
        return None
    player_id = record.player_data.id
    hs_struct = transform_highscore_struct(
        record=record,
        player_id=player_id,
    )
    data_to_predict = transform_data_to_predict_struct(
        player_id=player_id,
        hs_struct=hs_struct,
    )
    return data_to_predict
