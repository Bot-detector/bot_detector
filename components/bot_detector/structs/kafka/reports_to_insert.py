from bot_detector.structs._metadata import MetaData
from bot_detector.structs.reports import Detection
from pydantic import BaseModel


class ReportsToInsertStruct(BaseModel):
    metadata: MetaData
    report: Detection
