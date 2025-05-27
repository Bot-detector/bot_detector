from abc import ABC, abstractmethod

from bot_detector.structs import (
    HighscoreDataDailyStruct,
    HighscoreDataLatestStruct,
    HighscoreDataMonthlyStruct,
    HighscoreDataWeeklyStruct,
)
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


class HighscoreDataDailyInterface(ABC):
    @abstractmethod
    async def insert_highscore(
        self,
        async_session: AsyncSession,
        highscore_data: HighscoreDataDailyStruct,
    ) -> None:
        """Insert a new highscore record into the database."""
        raise NotImplementedError()


class HighscoreDataWeeklyInterface(ABC):
    @abstractmethod
    async def insert_highscore(
        self,
        async_session: AsyncSession,
        highscore_data: HighscoreDataWeeklyStruct,
    ):
        """Insert a new highscore record into the database."""
        raise NotImplementedError()


class HighscoreDataMonthlyInterface(ABC):
    @abstractmethod
    async def insert_highscore(
        self,
        async_session: AsyncSession,
        highscore_data: HighscoreDataMonthlyStruct,
    ):
        """Insert a new highscore record into the database."""
        raise NotImplementedError()
