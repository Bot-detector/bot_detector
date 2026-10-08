from abc import ABC, abstractmethod
from collections.abc import Sequence

from bot_detector.structs import (
    PredictionCreate,
    PredictionLatestRead,
    PredictionRead,
)
from sqlalchemy.ext.asyncio import AsyncSession


class PredictionLatestInterface(ABC):
    @abstractmethod
    async def select(
        self,
        async_session: AsyncSession,
    ) -> list[PredictionLatestRead]:
        raise NotImplementedError()

    @abstractmethod
    async def insert(
        self,
        async_session: AsyncSession,
        predictions: Sequence[PredictionCreate],
    ) -> None:
        raise NotImplementedError()


class PredictionInterface(ABC):
    @abstractmethod
    async def select(
        self,
        async_session: AsyncSession,
    ) -> list[PredictionRead]:
        raise NotImplementedError()

    @abstractmethod
    async def insert(
        self,
        async_session: AsyncSession,
        predictions: Sequence[PredictionCreate],
    ) -> None:
        raise NotImplementedError()
