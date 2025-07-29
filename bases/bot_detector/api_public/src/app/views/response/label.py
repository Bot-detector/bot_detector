from pydantic import BaseModel


class LabelResponse(BaseModel):
    id: int
    label: str
