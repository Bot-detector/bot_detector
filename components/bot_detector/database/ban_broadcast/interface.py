from abc import ABC, abstractmethod

from sqlalchemy.ext.asyncio import AsyncSession

from .structs import BanCounts, BannedBot


class BanBroadcastInterface(ABC):
    @abstractmethod
    async def get_ban_counts(self, async_session: AsyncSession) -> BanCounts:
        raise NotImplementedError()

    @abstractmethod
    async def select_banned_bots(self, async_session: AsyncSession) -> list[BannedBot]:
        raise NotImplementedError()

    @abstractmethod
    async def apply_bot_bans(self, async_session: AsyncSession) -> int:
        raise NotImplementedError()
