from typing import TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T", bound=BaseModel)


class InMemoryConfig(BaseModel):
    # ge=1: asyncio.Queue(0) means UNBOUNDED, silently disabling the bound
    maxsize: int = Field(default=100, ge=1)
