from bot_detector.structs._metadata import MetaData
from bot_detector.structs.reports import ParsedDetection
from pydantic import BaseModel


class ReportsToInsertStruct(BaseModel):
    metadata: MetaData
    report: ParsedDetection
