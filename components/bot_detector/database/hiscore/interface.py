from abc import ABC, abstractmethod

from bot_detector.structs import HighscoreDataLatestStruct
from sqlalchemy.ext.asyncio import AsyncSession


class HighscoreDataLatestInterface(ABC):
    @abstractmethod
    async def insert_highscore(
        self,
        async_session: AsyncSession,
        highscore_data: HighscoreDataLatestStruct,
    ) -> None:
        """Insert a new highscore record into the database."""
        raise NotImplementedError()

    @abstractmethod
    async def insert_highscore_many(
        self,
        async_session: AsyncSession,
        highscore_data: list[HighscoreDataLatestStruct],
    ) -> None:
        """Insert multiple highscore records into the database."""
        raise NotImplementedError()
