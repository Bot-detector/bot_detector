from .._metadata import MetaData
from bot_detector.report.structs import ParsedDetection
from pydantic import BaseModel


class ReportsToInsertStruct(BaseModel):
    metadata: MetaData
    report: ParsedDetection
