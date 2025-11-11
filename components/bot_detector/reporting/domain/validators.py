import logging
import time
from typing import Iterable, Optional

from bot_detector.structs import Detection

logger = logging.getLogger(__name__)


def check_data_size(data: list[Detection], *, max_size: int = 5000) -> Optional[list[Detection]]:
    if len(data) > max_size:
        logger.warning("invalid data size: %s > %s", len(data), max_size)
        return None
    return data


def filter_valid_time(data: list[Detection]) -> list[Detection]:
    current_time = int(time.time())
    min_ts = current_time - 25_200  # 7 hours ago
    max_ts = current_time + 3_600  # 1 hour ahead

    output: list[Detection] = []
    for detection in data:
        if detection.ts <= min_ts:
            logger.info(
                "invalid: %s <= %s now=%s reporter=%s",
                detection.ts,
                min_ts,
                current_time,
                detection.reporter,
            )
            continue
        if detection.ts >= max_ts:
            logger.info(
                "invalid: %s >= %s now=%s reporter=%s",
                detection.ts,
                max_ts,
                current_time,
                detection.reporter,
            )
            continue
        output.append(detection)
    return output


def check_unique_reporter(data: list[Detection]) -> Optional[list[Detection]]:
    unique_reporters = {d.reporter for d in data}
    if len(unique_reporters) <= 1:
        logger.warning("invalid unique reporter set=%s", unique_reporters)
        return None
    return data


def collect_player_names(detections: Iterable[Detection]) -> list[str]:
    players: set[str] = set()
    for detection in detections:
        players.add(detection.reported)
        players.add(detection.reporter)
    return list(players)
