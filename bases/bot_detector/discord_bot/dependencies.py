from dataclasses import dataclass
from typing import Optional

import aiohttp
from bot_detector.database.core import Settings as DatabaseSettings
from bot_detector.database.core import get_session_factory
from bot_detector.discord_bot.config import Settings
from bot_detector.osrs_items import OsrsItemsClient
from bot_detector.public_api import LegacyApiClient, PublicApiClient
from bot_detector.rate_limiter import RateLimiter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@dataclass
class BotDependencies:
    session: Optional[aiohttp.ClientSession] = None
    public_api: Optional[PublicApiClient] = None
    legacy_api: Optional[LegacyApiClient] = None
    osrs_items: Optional[OsrsItemsClient] = None
    session_factory: Optional[async_sessionmaker[AsyncSession]] = None

    def init_session(self, session: aiohttp.ClientSession | None = None):
        if self.session is None:
            self.session = session or aiohttp.ClientSession()

    def init_public_api(self):
        assert self.session is not None
        if self.public_api is None:
            self.public_api = PublicApiClient(session=self.session)

    def init_legacy_api(self, token: str, base_url: str | None = None):
        assert self.session is not None
        if self.legacy_api is None:
            self.legacy_api = LegacyApiClient(
                session=self.session,
                token=token,
                base_url=base_url,
                limiter=RateLimiter(calls_per_interval=500, interval=60),
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
        if settings.API_TOKEN:
            self.init_legacy_api(
                token=settings.API_TOKEN,
                base_url=settings.API_URL,
            )
        self.init_osrs_items(user_agent=settings.OSRS_ITEMS_USER_AGENT)
        assert isinstance(settings.DATABASE_URL, str)
        self.init_session_factory(sql_uri=settings.DATABASE_URL)

    def get_session(self) -> aiohttp.ClientSession:
        assert self.session is not None
        return self.session

    def get_public_api(self) -> PublicApiClient:
        assert self.public_api is not None
        return self.public_api

    def get_legacy_api(self) -> LegacyApiClient:
        assert self.legacy_api is not None
        return self.legacy_api

    def get_osrs_items(self) -> OsrsItemsClient:
        assert self.osrs_items is not None
        return self.osrs_items

    def get_session_factory(self) -> async_sessionmaker[AsyncSession]:
        assert self.session_factory is not None
        return self.session_factory


DEPS = BotDependencies()
