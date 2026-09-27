import asyncio
import logging
from typing import Any

import aiohttp
from pydantic import BaseModel

logger = logging.getLogger(__name__)

DISCORD_API_BASE = "https://discord.com/api/v10"
DEFAULT_TIMEOUT_S = 10.0


class DiscordUser(BaseModel):
    id: str
    username: str
    discriminator: str | None = None


class DiscordOAuthError(Exception):
    """Raised when a discord access token cannot be validated."""


class DiscordOAuth:
    """Validates discord access tokens by resolving the user identity.

    The OAuth2 flow itself (PKCE, token exchange, refresh) runs entirely
    in the client; the api only ever sees an access token and confirms
    it is live via GET /users/@me.
    """

    def __init__(
        self,
        http: aiohttp.ClientSession,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ):
        self._http = http
        self._timeout = aiohttp.ClientTimeout(total=timeout_s)

    async def get_current_user(self, access_token: str) -> DiscordUser | Exception:
        try:
            user: dict[str, Any] = await self._get(
                path="/users/@me",
                token=access_token,
            )
            return DiscordUser.model_validate(user)
        except DiscordOAuthError as e:
            return e
        except (aiohttp.ClientError, ValueError, TypeError) as e:
            return DiscordOAuthError(f"fetch user failed: {e}")

    async def _get(self, path: str, token: str) -> dict[str, Any]:
        url = f"{DISCORD_API_BASE}{path}"
        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with self._http.get(
                url, headers=headers, timeout=self._timeout
            ) as response:
                body = await response.json()
        except asyncio.TimeoutError as e:
            raise DiscordOAuthError(
                f"GET {path} timed out after {self._timeout.total}s"
            ) from e
        if response.status != 200:
            raise DiscordOAuthError(f"GET {path} returned {response.status}: {body}")
        if not isinstance(body, dict):
            raise DiscordOAuthError(f"GET {path} returned non-dict body")
        return body
