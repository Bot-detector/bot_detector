from pydantic import BaseModel

class Ok(BaseModel):
    detail: str = "ok"