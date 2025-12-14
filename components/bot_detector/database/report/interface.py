from abc import ABC, abstractmethod

from bot_detector.structs import ParsedDetection
from sqlalchemy.ext.asyncio import AsyncSession


class ReportInterface(ABC):
    @abstractmethod
    async def select(
        self,
        async_session: AsyncSession,
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def update(
        self,
        async_session: AsyncSession,
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def insert(
        self,
        async_session: AsyncSession,
        reports: list[ParsedDetection],
    ) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def delete(
        self,
        async_session: AsyncSession,
    ) -> None:
        raise NotImplementedError()
