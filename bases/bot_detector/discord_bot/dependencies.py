from dataclasses import dataclass
from typing import Optional

import aiohttp
from bot_detector.database.core import Settings as DatabaseSettings
from bot_detector.database.core import get_session_factory
from bot_detector.discord_bot.config import Settings
from bot_detector.osrs_items import OsrsItemsClient
from bot_detector.public_api import PublicApiClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


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
            self.public_api = PublicApiClient(
                session=self.session,
                token=Settings().API_TOKEN,
            )

    def init_osrs_items(self, user_agent: str):
        assert self.session is not None
        if self.osrs_items is None:
            self.osrs_items = OsrsItemsClient(
                session=self.session,
                user_agent=user_agent,
            )

    def init_session_factory(self, sql_uri: str):
        if self.session_factory is None:
            async_session, async_engine = get_session_factory(DatabaseSettings())
            self.session_factory = async_session
            self.async_engine = async_engine

    def init(self, settings: Settings, session: Optional[aiohttp.ClientSession] = None):
        self.init_session(session)
        self.init_public_api()
        self.init_osrs_items(user_agent=settings.OSRS_ITEMS_USER_AGENT)
        assert isinstance(settings.DATABASE_URL, str)
        self.init_session_factory(sql_uri=settings.DATABASE_URL)

    def get_session(self) -> aiohttp.ClientSession:
        assert self.session is not None
        return self.session

    def get_public_api(self) -> PublicApiClient:
        assert self.public_api is not None
        return self.public_api

    def get_osrs_items(self) -> OsrsItemsClient:
        assert self.osrs_items is not None
        return self.osrs_items

    def get_session_factory(self) -> async_sessionmaker[AsyncSession]:
        assert self.session_factory is not None
        return self.session_factory


DEPS = BotDependencies()
