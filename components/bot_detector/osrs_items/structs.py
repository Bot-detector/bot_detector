
from pydantic import BaseModel


class ItemStruct(BaseModel):
    id: int
    name: str
    examine: str | None = None
    members: bool
    lowalch: int | None = None
    highalch: int | None = None
    limit: int | None = None
    value: int | None = None
    icon: str | None = None


class ItemsDictStruct(BaseModel):
    items: list[ItemStruct]
