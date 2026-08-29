from abc import ABC, abstractmethod

from bot_detector.database.discord.structs import DiscordVerificationTableStruct
from sqlalchemy.ext.asyncio import AsyncSession


class DiscordVerificationInterface(ABC):
    @abstractmethod
    async def get_verified_player(
        self,
        async_session: AsyncSession,
        discord_id: str | None = None,
        player_id: int | None = None,
        is_verified: bool | None = None,
    ) -> DiscordVerificationTableStruct | None:
        pass

    @abstractmethod
    async def get_linked_accounts(
        self,
        async_session: AsyncSession,
        discord_id: str,
    ) -> list[DiscordVerificationTableStruct]:
        pass

    @abstractmethod
    async def create_verification(
        self,
        async_session: AsyncSession,
        discord_id: str,
        player_id: int,
        code: str,
        auto_commit: bool = True,
    ) -> None:
        pass

    @abstractmethod
    async def update_verification_status(
        self,
        async_session: AsyncSession,
        discord_id: str,
        player_id: int,
        verified_status: int,
        auto_commit: bool = True,
    ) -> bool:
        pass

    @abstractmethod
    async def set_primary_rsn(
        self,
        async_session: AsyncSession,
        discord_id: str,
        player_id: int,
        is_primary: bool,
        auto_commit: bool = True,
    ) -> bool:
        pass

    @abstractmethod
    async def delete_verification(
        self,
        async_session: AsyncSession,
        discord_id: str,
        player_id: int,
        auto_commit: bool = True,
    ) -> bool:
        pass
