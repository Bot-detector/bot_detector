from abc import ABC, abstractmethod

from bot_detector.structs import (
    HighscoreDataDailyStruct,
    HighscoreDataMonthlyStruct,
    HighscoreDataWeeklyStruct,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class HighscoreDataDailyInterface(ABC):
    @abstractmethod
    async def insert_highscore(
        self,
        async_session: async_sessionmaker[AsyncSession],
        highscore_data: HighscoreDataDailyStruct,
    ) -> None:
        """Insert a new highscore record into the database."""
        raise NotImplementedError()


class HighscoreDataWeeklyInterface(ABC):
    @abstractmethod
    async def insert_highscore(
        self,
        async_session: async_sessionmaker[AsyncSession],
        highscore_data: HighscoreDataWeeklyStruct,
    ):
        """Insert a new highscore record into the database."""
        raise NotImplementedError()


class HighscoreDataMonthlyInterface(ABC):
    @abstractmethod
    async def insert_highscore(
        self,
        async_session: async_sessionmaker[AsyncSession],
        highscore_data: HighscoreDataMonthlyStruct,
    ):
        """Insert a new highscore record into the database."""
        raise NotImplementedError()
