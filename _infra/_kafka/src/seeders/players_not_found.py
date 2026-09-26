import random
from typing import Generator

from pydantic import BaseModel

from seeders.players_to_scrape import MetaData, PlayerStruct


class NotFoundStruct(BaseModel):
    metadata: MetaData
    player_data: PlayerStruct


def create_players_not_found(
    players: list[PlayerStruct], count: int
) -> Generator[NotFoundStruct, None, None]:
    if count > len(players):
        players = players * (count // len(players) + 1)

    for player in random.sample(players, count):
        yield NotFoundStruct(
            metadata=MetaData(version=0, source="init"),
            player_data=player.model_copy(deep=True),
        )
