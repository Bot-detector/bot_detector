import logging
from typing import Optional

from bot_detector.database.repositories import (
    HighscoreDataDailyRepo,
    HighscoreDataLatestRepo,
    HighscoreDataMonthlyRepo,
    HighscoreDataWeeklyRepo,
    PlayerRepo,
)
from bot_detector.structs import HighscoreBaseStruct, ScrapedStruct
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..domain.ttl import set_ttl

logger = logging.getLogger(__name__)


class HighscoreWorkerService:
    """Encapsulates the orchestration for persisting scraped highscore data."""

    def __init__(
        self,
        player_repo: Optional[PlayerRepo] = None,
        hs_repo_latest: Optional[HighscoreDataLatestRepo] = None,
        hs_repo_daily: Optional[HighscoreDataDailyRepo] = None,
        hs_repo_weekly: Optional[HighscoreDataWeeklyRepo] = None,
        hs_repo_monthly: Optional[HighscoreDataMonthlyRepo] = None,
    ) -> None:
        self.player_repo = player_repo or PlayerRepo()
        self.hs_repo_latest = hs_repo_latest or HighscoreDataLatestRepo()
        self.hs_repo_daily = hs_repo_daily or HighscoreDataDailyRepo()
        self.hs_repo_weekly = hs_repo_weekly or HighscoreDataWeeklyRepo()
        self.hs_repo_monthly = hs_repo_monthly or HighscoreDataMonthlyRepo()

    async def persist_scraped_data(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        scraped_data: ScrapedStruct,
    ) -> None:
        player_data = scraped_data.player_data
        hs_data = scraped_data.highscore_data

        async with session_factory() as session:
            async with session.begin():
                await self.player_repo.update_player(
                    async_session=session,
                    player_data=player_data,
                )

                if hs_data is not None:
                    await self._persist_highscores(
                        session=session,
                        highscore_data=hs_data,
                    )
            await session.commit()

    async def _persist_highscores(
        self,
        session: AsyncSession,
        highscore_data: HighscoreBaseStruct,
    ) -> None:
        hs_daily = set_ttl(data=highscore_data, table="daily")
        hs_weekly = set_ttl(data=highscore_data, table="weekly")
        hs_monthly = set_ttl(data=highscore_data, table="monthly")

        await self.hs_repo_latest.insert_highscore(
            async_session=session,
            highscore_data=highscore_data,
        )
        await self.hs_repo_daily.insert_highscore(
            async_session=session,
            highscore_data=hs_daily,
        )
        await self.hs_repo_weekly.insert_highscore(
            async_session=session,
            highscore_data=hs_weekly,
        )
        await self.hs_repo_monthly.insert_highscore(
            async_session=session,
            highscore_data=hs_monthly,
        )

    def should_skip(self, scraped_data: ScrapedStruct) -> bool:
        """Return True if the scraped payload should be skipped."""
        name = scraped_data.player_data.name
        if len(name) > 13:
            logger.debug("Skipping player %s due to name length", name)
            return True
        return False
