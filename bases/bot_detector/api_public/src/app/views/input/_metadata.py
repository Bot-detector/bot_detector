from pydantic import BaseModel


class Metadata(BaseModel):
    version: str
