import logging

from bot_detector.event_queue.structs import ReportsToInsertStruct
from bot_detector.structs import ParsedDetection

logger = logging.getLogger(__name__)


def transform_report(record: ReportsToInsertStruct) -> ParsedDetection | None:
    if record.metadata.version != 1:
        logger.warning(f"Unsupported report version: {record.metadata.version}")
        return None
    return record.report
