from abc import ABC, abstractmethod

from bot_detector.player.structs import PlayerStruct
from sqlalchemy.ext.asyncio import AsyncSession


class playerInterface(ABC):
    @abstractmethod
    async def insert_player(self, player_data):
        """Insert a new player into the database."""
        raise NotImplementedError()

    @abstractmethod
    async def select_player(
        self,
        async_session: AsyncSession,
        days: int = 7,
        confirmed_ban: bool | None = None,
        player_id: int | None = None,
        limit: int = 10_000,
    ) -> list[PlayerStruct]:
        """Select a player from the database by player_id."""
        pass

    @abstractmethod
    async def update_player(self, player_id: int, player_data: PlayerStruct):
        """Update an existing player in the database."""
        raise NotImplementedError()

    @abstractmethod
    async def delete_player(self, player_id: int):
        """Delete a player from the database by player_id."""
        raise NotImplementedError()
