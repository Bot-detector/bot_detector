from abc import ABC, abstractmethod

from bot_detector.database.api.structs import ApiUserTableStruct
from sqlalchemy.ext.asyncio import AsyncSession


class ApiUserInterface(ABC):
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
        permission: str,
        token: str,
        user_name: str | None = None,
        user_id: int | None = None,
    ) -> bool:
        pass

    @abstractmethod
    async def get_user(
        self,
        async_session: AsyncSession,
        user_name: str,
        is_active: bool | None = None,
    ) -> ApiUserTableStruct | None:
        pass
