import logging
from typing import Optional

import aiohttp
from bot_detector.database.discord import DiscordVerificationRepo
from bot_detector.discord_bot.config import Settings
from bot_detector.osrs_items import OsrsItemsClient
from bot_detector.public_api import PublicApiClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

logger = logging.getLogger(__name__)


class BotDependencies:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.session = aiohttp.ClientSession()
        self.public_api = PublicApiClient(session=self.session)
        self.osrs_items = OsrsItemsClient(
            session=self.session, user_agent=settings.OSRS_ITEMS_USER_AGENT
        )

        if settings.SQL_URI:
            engine = create_async_engine(settings.SQL_URI, echo=False)
            self.session_factory: Optional[async_sessionmaker[AsyncSession]] = (
                async_sessionmaker(
                    engine,
                    class_=AsyncSession,
                    expire_on_commit=False,
                )
            )
            self.discord_repo: Optional[DiscordVerificationRepo] = (
                DiscordVerificationRepo()
            )
        else:
            self.session_factory = None
            self.discord_repo = None
            logger.warning("No SQL_URI configured, database features disabled")


DEPS = BotDependencies(Settings())
