from dataclasses import dataclass
from typing import Optional

import aiohttp
from bot_detector.discord_bot.config import Settings
from bot_detector.osrs_items import OsrsItemsClient
from bot_detector.public_api import PublicApiClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@dataclass
class BotDependencies:
    session: Optional[aiohttp.ClientSession] = None
    public_api: Optional[PublicApiClient] = None
    osrs_items: Optional[OsrsItemsClient] = None
    session_factory: Optional[async_sessionmaker[AsyncSession]] = None

    def init_session(self, session: aiohttp.ClientSession | None = None):
        if self.session is None:
            self.session = session or aiohttp.ClientSession()

    def init_public_api(self):
        assert self.session is not None
        if self.public_api is None:
            self.public_api = PublicApiClient(session=self.session)

    def init_osrs_items(self, user_agent: str):
        assert self.session is not None
        if self.osrs_items is None:
            self.osrs_items = OsrsItemsClient(
                session=self.session,
                user_agent=user_agent,
            )

    def init_session_factory(self, sql_uri: str):
        if self.session_factory is None:
            engine = create_async_engine(sql_uri, echo=False)
            self.session_factory = async_sessionmaker(
                engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )

    def init(self, settings: Settings, session: Optional[aiohttp.ClientSession] = None):
        self.init_session(session)
        self.init_public_api()
        self.init_osrs_items(user_agent=settings.OSRS_ITEMS_USER_AGENT)
        assert isinstance(settings.DATABASE_URL, str)
        self.init_session_factory(sql_uri=settings.DATABASE_URL)


DEPS = BotDependencies()
