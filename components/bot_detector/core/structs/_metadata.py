from pydantic import BaseModel


class MetaData(BaseModel):
    version: int
    source: str
