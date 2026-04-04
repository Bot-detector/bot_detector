import random
from datetime import datetime
from typing import Generator

from pydantic import BaseModel


class Player(BaseModel):
    id: int
    name: str
    created_at: datetime
    updated_at: datetime | None
    possible_ban: int
    confirmed_ban: int
    confirmed_player: int
    label_id: int
    label_jagex: int


def create_players(names: list[str], count: int) -> Generator[Player, None, None]:
    if count > len(names):
        names = names * (count // len(names) + 1)

    selected_names = names[:count]

    for idx, name in enumerate(selected_names, start=1):
        yield Player(
            id=idx,
            name=name,
            created_at=datetime.fromtimestamp(random.randint(1609459200, 1735689600)),
            updated_at=None,
            possible_ban=0,
            confirmed_ban=0,
            confirmed_player=0,
            label_id=0,
            label_jagex=0,
        )
