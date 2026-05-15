from abc import ABC, abstractmethod

from bot_detector.database.api.structs import ApiUserTableStruct
from sqlalchemy.ext.asyncio import AsyncSession


class ApiUserInterface(ABC):
    @abstractmethod
    async def get_by_user_name(
        self,
        async_session: AsyncSession,
        user_name: str,
    ) -> ApiUserTableStruct | None:
        pass

    @abstractmethod
    async def log_usage(
        self,
        async_session: AsyncSession,
        user_id: int,
        route: str,
        auto_commit: bool = True,
    ) -> None:
        pass

    @abstractmethod
    async def has_permission(
        self,
        async_session: AsyncSession,
        user_name: str,
        token: str,
        permission: str,
    ) -> bool:
        pass
