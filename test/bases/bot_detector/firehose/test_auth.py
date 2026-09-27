import pytest
from bot_detector.database.api.interface import ApiUserInterface
from bot_detector.database.api.structs import ApiUserTableStruct
from bot_detector.firehose.app.auth.auth import (
    ANONYMOUS,
    WILDCARD_SCOPE,
    ApiKeyAuthRepo,
    AuthUser,
    Identity,
    InvalidApiKey,
    firehose_permission,
)
from bot_detector.firehose.app.auth.discord import DiscordOAuth, DiscordUser
from bot_detector.firehose.core.config import Settings

TOPIC = "players.scraped"


class FakeUserRepo(ApiUserInterface):
    def __init__(
        self,
        row: ApiUserTableStruct | None,
        permissions: list[str] | None = None,
    ):
        self.row = row
        self.permissions = permissions or []

    async def log_usage(self, async_session, user_id, route, auto_commit=True):
        raise NotImplementedError

    async def has_permission(
        self, async_session, permission, token=None, user_name=None, user_id=None
    ):
        return permission in self.permissions

    async def get_user(self, async_session, user_name, is_active=None):
        return self.row

    async def get_permissions(self, async_session, user_id):
        return self.permissions


class FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class FakeSessionFactory:
    def __call__(self):
        return FakeSession()


class FakeOAuth(DiscordOAuth):
    def __init__(self, result: DiscordUser | Exception):
        self.result = result

    async def get_current_user(self, access_token: str):
        return self.result


def make_repo(
    row: ApiUserTableStruct | None = None,
    permissions: list[str] | None = None,
    oauth_result: DiscordUser | Exception | None = None,
    with_db: bool = True,
) -> ApiKeyAuthRepo:
    repo = ApiKeyAuthRepo(
        settings=Settings(),
        session_factory=FakeSessionFactory() if with_db else None,
        user_repo=FakeUserRepo(row=row, permissions=permissions),
    )
    if oauth_result is None and with_db:
        oauth_result = DiscordUser(id="123", username="someone")
    if oauth_result is not None:
        repo.discord_oauth = FakeOAuth(result=oauth_result)
    return repo


def make_row(username: str = "discord_123") -> ApiUserTableStruct:
    return ApiUserTableStruct(
        username=username, token="legacy-not-used", is_active=True
    )


@pytest.mark.asyncio
async def test_authenticate_no_key_returns_anonymous():
    repo = make_repo(with_db=False)
    assert await repo.authenticate(api_key=None, topic=TOPIC) == ANONYMOUS
    assert await repo.authenticate(api_key="", topic=TOPIC) == ANONYMOUS


@pytest.mark.asyncio
async def test_authenticate_static_dev_key_returns_wildcard_scope():
    repo = make_repo(with_db=False)
    user = await repo.authenticate(api_key="changeme-key-one", topic=TOPIC)
    assert user == AuthUser(name="system-one", scopes=[WILDCARD_SCOPE])


@pytest.mark.asyncio
async def test_authenticate_unknown_key_without_db_is_invalid():
    repo = make_repo(with_db=False)
    user = await repo.authenticate(api_key="whatever", topic=TOPIC)
    assert isinstance(user, InvalidApiKey)


@pytest.mark.asyncio
async def test_authenticate_discord_invalid_token_is_403():
    repo = make_repo(oauth_result=RuntimeError("bad token"))
    user = await repo.authenticate(api_key="some-discord-token", topic=TOPIC)
    assert isinstance(user, InvalidApiKey)


@pytest.mark.asyncio
async def test_authenticate_registered_and_allowlisted_returns_scopes():
    scopes = [firehose_permission(TOPIC), "discord_general"]
    repo = make_repo(row=make_row(), permissions=scopes)
    user = await repo.authenticate(api_key="discord-access-token", topic=TOPIC)
    assert user == AuthUser(name="discord_123", scopes=scopes)


@pytest.mark.asyncio
async def test_authenticate_registered_without_topic_permission_is_403():
    repo = make_repo(row=make_row(), permissions=["discord_general"])
    user = await repo.authenticate(api_key="discord-access-token", topic=TOPIC)
    assert isinstance(user, InvalidApiKey)


@pytest.mark.asyncio
async def test_authenticate_registered_without_permissions_is_403():
    repo = make_repo(row=make_row(), permissions=[])
    user = await repo.authenticate(api_key="discord-access-token", topic=TOPIC)
    assert isinstance(user, InvalidApiKey)


@pytest.mark.asyncio
async def test_authenticate_unregistered_discord_user_is_403():
    repo = make_repo(row=None, permissions=[firehose_permission(TOPIC)])
    user = await repo.authenticate(api_key="discord-access-token", topic=TOPIC)
    assert isinstance(user, InvalidApiKey)


@pytest.mark.asyncio
async def test_authenticate_db_failure_is_403():
    class BrokenRepo(FakeUserRepo):
        async def get_user(self, async_session, user_name, is_active=None):
            raise RuntimeError("db down")

    repo = ApiKeyAuthRepo(
        settings=Settings(),
        session_factory=FakeSessionFactory(),
        user_repo=BrokenRepo(row=None, permissions=[]),
    )
    repo.discord_oauth = FakeOAuth(result=DiscordUser(id="123", username="someone"))
    user = await repo.authenticate(api_key="discord-access-token", topic=TOPIC)
    assert isinstance(user, InvalidApiKey)


@pytest.mark.asyncio
async def test_identify_no_key_returns_anonymous_allowed():
    repo = make_repo(with_db=False)
    identity = await repo.identify(api_key=None)
    assert identity == Identity(user="anonymous", allowed=True, scopes=[])


@pytest.mark.asyncio
async def test_identify_static_dev_key_returns_wildcard():
    repo = make_repo(with_db=False)
    identity = await repo.identify(api_key="changeme-key-one")
    assert identity == Identity(
        user="system-one", allowed=True, scopes=[WILDCARD_SCOPE]
    )


@pytest.mark.asyncio
async def test_identify_invalid_discord_token_is_unknown_and_rejected():
    repo = make_repo(oauth_result=RuntimeError("bad token"))
    identity = await repo.identify(api_key="some-discord-token")
    assert identity == Identity(user=None, allowed=False, scopes=[])


@pytest.mark.asyncio
async def test_identify_unregistered_discord_user_is_known_and_rejected():
    repo = make_repo(row=None)
    identity = await repo.identify(api_key="discord-access-token")
    assert identity == Identity(user="discord_123", allowed=False, scopes=[])


@pytest.mark.asyncio
async def test_identify_registered_returns_all_scopes():
    scopes = [firehose_permission(TOPIC), "discord_general"]
    repo = make_repo(row=make_row(), permissions=scopes)
    identity = await repo.identify(api_key="discord-access-token")
    assert identity == Identity(user="discord_123", allowed=True, scopes=scopes)


@pytest.mark.asyncio
async def test_identify_registered_without_firehose_permission_is_allowed():
    repo = make_repo(row=make_row(), permissions=["discord_general"])
    identity = await repo.identify(api_key="discord-access-token")
    assert identity == Identity(
        user="discord_123", allowed=True, scopes=["discord_general"]
    )


@pytest.mark.asyncio
async def test_identify_db_failure_is_unknown_and_rejected():
    class BrokenRepo(FakeUserRepo):
        async def get_user(self, async_session, user_name, is_active=None):
            raise RuntimeError("db down")

    repo = ApiKeyAuthRepo(
        settings=Settings(),
        session_factory=FakeSessionFactory(),
        user_repo=BrokenRepo(row=None, permissions=[]),
    )
    repo.discord_oauth = FakeOAuth(result=DiscordUser(id="123", username="someone"))
    identity = await repo.identify(api_key="discord-access-token")
    assert identity == Identity(user=None, allowed=False, scopes=[])
