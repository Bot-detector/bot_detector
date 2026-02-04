from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class InMemoryConfig(BaseModel):
    maxsize: int = 100
