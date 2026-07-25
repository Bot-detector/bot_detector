import random
from collections.abc import Generator

from pydantic import BaseModel
from seeders.players_to_scrape import PlayerStruct


class MetaData(BaseModel):
    version: int
    source: str


class PlayerBannedStruct(BaseModel):
    metadata: MetaData
    player_id: int
    name: str


def create_players_banned(
    players: list[PlayerStruct], count: int
) -> Generator[PlayerBannedStruct, None, None]:
    for player in random.sample(players, min(count, len(players))):
        yield PlayerBannedStruct(
            metadata=MetaData(version=1, source="init"),
            player_id=player.id,
            name=player.name,
        )
