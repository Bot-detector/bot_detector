import logging
from typing import Any

from bot_detector.event_queue.structs import (
    DataToPredictStruct,
    HighScoreStruct,
    ScrapedStruct,
    map_highscore_keys,
)

logger = logging.getLogger(__name__)


def clean_dict(data: dict[str, Any]) -> dict[str, Any]:
    """
    Cleans a dictionary by mapping keys to struct field names and removing entries with None values.

    Args:
        - data: dict with string keys and any type of values
    Returns:
        - dict with field names (e.g. "abyssal sire" -> "abyssal_sire") and no None values
    Raises:
        - TypeError if input is not a dictionary
    """
    if not isinstance(data, dict):
        raise TypeError("Input must be a dictionary")
    return map_highscore_keys(data)


def transform_highscore_struct(record: ScrapedStruct) -> HighScoreStruct:
    """
    Transforms the highscore data from the ScrapedStruct into a HighScoreStruct.

    Args:
        - record: ScrapedStruct containing the highscore data
    Returns:
        - HighScoreStruct if transformation is successful
    Raises:
        - ValueError if highscore data is None
        - ValidationError if the data cannot be validated into a HighScoreStruct
    """
    if record.highscore_data is None:
        raise ValueError("Highscore data is None")

    skills = clean_dict(record.highscore_data.skills or {})
    activities = clean_dict(record.highscore_data.activities or {})
    return HighScoreStruct.model_validate(skills | activities)


def transform_data_to_predict_struct(
    player_id: int, hs_struct: HighScoreStruct
) -> DataToPredictStruct:
    """
    Transforms the player_id and highscore struct into a DataToPredictStruct.

    Args:
        - player_id: int representing the player's ID
        - hs_struct: HighScoreStruct containing the player's highscore data
    Returns:
        - DataToPredictStruct if transformation is successful
    Raises:
        - ValidationError if the data cannot be validated into a DataToPredictStruct
    """
    data = {"player_id": player_id, "data": hs_struct}
    return DataToPredictStruct.model_validate(data)


def transform_scraped_struct(record: ScrapedStruct) -> DataToPredictStruct | None:
    """
    Transforms a ScrapedStruct into a DataToPredictStruct if highscore data is present, otherwise returns None.

    Args:
        - record: ScrapedStruct containing the player's scraped data
    Returns:
        - DataToPredictStruct if highscore data is present and transformation is successful, otherwise None
    Raises:
        - ValidationError if the data cannot be validated into a DataToPredictStruct
    """
    if record.highscore_data is None:
        logger.debug("Highscore data is None")
        return None

    player_id = record.player_data.id
    hs_struct = transform_highscore_struct(record=record)
    data_to_predict = transform_data_to_predict_struct(
        player_id=player_id,
        hs_struct=hs_struct,
    )
    return data_to_predict
