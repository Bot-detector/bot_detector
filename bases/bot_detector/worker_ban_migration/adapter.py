import logging

from bot_detector.event_queue.structs import PlayerBannedStruct

logger = logging.getLogger(__name__)


def transform_player_banned(record: PlayerBannedStruct) -> int | None:
    if record.metadata.version != 1:
        logger.warning(f"Unsupported player_banned version: {record.metadata.version}")
        return None
    return record.player_id
