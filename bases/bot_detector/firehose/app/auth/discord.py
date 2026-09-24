import logging
from typing import Any
from urllib.parse import urlencode

import aiohttp
from pydantic import BaseModel

logger = logging.getLogger(__name__)

DISCORD_API_BASE = "https://discord.com/api/v10"
DISCORD_AUTHORIZE_URL = "https://discord.com/oauth2/authorize"


class DiscordUser(BaseModel):
    id: str
    username: str
    discriminator: str | None = None


class DiscordToken(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    refresh_token: str | None = None
    scope: str | None = None


class DiscordOAuthError(Exception):
    """Raised when the Discord OAuth flow fails."""


class DiscordOAuth:
    """Client for the Discord OAuth2 flow.

    Building block for browser logins: exchange an authorization code for
    a token, then fetch the user identity.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        http: aiohttp.ClientSession,
    ):
        self._client_id = client_id
        self._client_secret = client_secret
        self._http = http

    def authorization_url(
        self,
        redirect_uri: str,
        scope: str = "identify",
        state: str | None = None,
    ) -> str:
        """Build the URL a browser should be redirected to.

        Per the OAuth2 docs, `state` is optional but recommended (CSRF
        protection): validate that it matches when handling the redirect.
        """
        params: dict[str, str] = {
            "response_type": "code",
            "client_id": self._client_id,
            "scope": scope,
            "redirect_uri": redirect_uri,
        }
        if state is not None:
            params["state"] = state
        query = urlencode(params)
        return f"{DISCORD_AUTHORIZE_URL}?{query}"

    async def exchange_code(
        self, code: str, redirect_uri: str
    ) -> DiscordToken | Exception:
        data = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        }
        try:
            token: dict[str, Any] = await self._post(path="/oauth2/token", data=data)
            return DiscordToken.model_validate(token)
        except DiscordOAuthError as e:
            return e
        except (aiohttp.ClientError, ValueError, TypeError) as e:
            return DiscordOAuthError(f"token exchange failed: {e}")

    async def client_credentials_token(
        self, scope: str = "identify"
    ) -> DiscordToken | Exception:
        """Get a bearer token for the app owner (no user interaction)."""
        data = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "grant_type": "client_credentials",
            "scope": scope,
        }
        try:
            token: dict[str, Any] = await self._post(path="/oauth2/token", data=data)
            return DiscordToken.model_validate(token)
        except DiscordOAuthError as e:
            return e
        except (aiohttp.ClientError, ValueError, TypeError) as e:
            return DiscordOAuthError(f"client credentials grant failed: {e}")

    async def refresh_token(self, refresh_token: str) -> DiscordToken | Exception:
        data = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        try:
            token: dict[str, Any] = await self._post(path="/oauth2/token", data=data)
            return DiscordToken.model_validate(token)
        except DiscordOAuthError as e:
            return e
        except (aiohttp.ClientError, ValueError, TypeError) as e:
            return DiscordOAuthError(f"token refresh failed: {e}")

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

    async def _post(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        url = f"{DISCORD_API_BASE}{path}"
        async with self._http.post(url, data=data) as response:
            body = await response.json()
            if response.status != 200:
                raise DiscordOAuthError(
                    f"POST {path} returned {response.status}: {body}"
                )
            if not isinstance(body, dict):
                raise DiscordOAuthError(f"POST {path} returned non-dict body")
            return body

    async def _get(self, path: str, token: str) -> dict[str, Any]:
        url = f"{DISCORD_API_BASE}{path}"
        headers = {"Authorization": f"Bearer {token}"}
        async with self._http.get(url, headers=headers) as response:
            body = await response.json()
            if response.status != 200:
                raise DiscordOAuthError(
                    f"GET {path} returned {response.status}: {body}"
                )
            if not isinstance(body, dict):
                raise DiscordOAuthError(f"GET {path} returned non-dict body")
            return body
