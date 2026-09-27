import logging
from typing import Any, Protocol

from bot_detector.database.api.interface import ApiUserInterface
from bot_detector.database.api.repository import ApiUserRepo
from bot_detector.firehose.app.auth.discord import DiscordOAuth
from bot_detector.firehose.core.config import Settings
from pydantic import BaseModel

logger = logging.getLogger(__name__)

ANONYMOUS_USER = "anonymous"
WILDCARD_SCOPE = "firehose.*"


def firehose_permission(topic: str) -> str:
    """Topic-specific permission granting a keyed firehose group."""
    return f"firehose.{topic}"


class AuthUser(BaseModel):
    name: str
    scopes: list[str] = []


ANONYMOUS = AuthUser(name=ANONYMOUS_USER, scopes=[])


class Identity(BaseModel):
    """Credential validation result without a topic gate.

    - user None + not allowed  -> credential invalid (identity unknown)
    - user set + not allowed   -> identity known but not allowlisted
    - allowed                  -> registered; scopes hold every permission
    """

    user: str | None = None
    allowed: bool = False
    scopes: list[str] = []


class InvalidApiKey(Exception):
    """Credential is not a valid discord token, or the identity is not
    registered / not allowlisted for a keyed group."""


class SessionFactoryProtocol(Protocol):
    def __call__(self) -> Any: ...


class AuthRepoProtocol(Protocol):
    async def identify(self, api_key: str | None) -> Identity: ...

    async def authenticate(
        self, api_key: str | None, topic: str
    ) -> AuthUser | Exception: ...


class ApiKeyAuthRepo:
    """Stateless auth: the credential is the discord access token.

    The token lives entirely client-side (PKCE); this repo only
    validates it on every request:

    - identify(api_key)  -> credential validation without a topic gate
      (used by GET /me)
    - authenticate(api_key, topic) -> identify + `firehose.{topic}`
      permission gate (used by the websocket)

    Static dev keys from settings are checked first and hold the
    wildcard scope.
    """

    def __init__(
        self,
        settings: Settings,
        session_factory: SessionFactoryProtocol | None = None,
        user_repo: ApiUserInterface | None = None,
    ):
        self._settings = settings
        self._session_factory = session_factory
        self._user_repo = user_repo or ApiUserRepo()
        self.discord_oauth: DiscordOAuth | None = None

    async def identify(self, api_key: str | None) -> Identity:
        """Validate a credential without a topic gate.

        - no credential            -> anonymous, allowed
        - static dev key           -> allowed, wildcard scope
        - invalid discord token    -> not allowed, identity unknown
        - not registered/allowlisted
          (apiUser.username = f"discord_{id}", active) -> not allowed,
          identity known
        - registered               -> allowed, every permission held

        The legacy apiUser.token column is never read or issued.
        """
        if not api_key:
            return Identity(user=ANONYMOUS_USER, allowed=True, scopes=[])

        name = self._settings.api_keys.get(api_key)
        if name is not None:
            return Identity(user=name, allowed=True, scopes=[WILDCARD_SCOPE])

        if self.discord_oauth is None or self._session_factory is None:
            return Identity(user=None, allowed=False, scopes=[])

        duser = await self.discord_oauth.get_current_user(access_token=api_key)
        if isinstance(duser, Exception):
            logger.info(f"discord token rejected: {duser}")
            return Identity(user=None, allowed=False, scopes=[])

        username = f"discord_{duser.id}"
        try:
            async with self._session_factory() as session:
                row = await self._user_repo.get_user(
                    async_session=session, user_name=username, is_active=True
                )
                if row is None:
                    return Identity(user=username, allowed=False, scopes=[])
                scopes = await self._user_repo.get_permissions(
                    async_session=session, user_id=row.id
                )
        except Exception as e:
            logger.warning(f"db auth failed: {e}")
            return Identity(user=None, allowed=False, scopes=[])
        return Identity(user=username, allowed=True, scopes=scopes)

    async def authenticate(
        self, api_key: str | None, topic: str
    ) -> AuthUser | Exception:
        if not api_key:
            return ANONYMOUS
        identity = await self.identify(api_key=api_key)
        if not identity.allowed or identity.user is None:
            return InvalidApiKey("not allowlisted")
        if (
            firehose_permission(topic) not in identity.scopes
            and WILDCARD_SCOPE not in identity.scopes
        ):
            return InvalidApiKey("not allowlisted")
        return AuthUser(name=identity.user, scopes=identity.scopes)
