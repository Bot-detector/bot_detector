from urllib.parse import parse_qs, urlparse

import pytest
from aiohttp import ClientSession
from aioresponses import aioresponses
from bot_detector.firehose.app.auth.discord import (
    DISCORD_API_BASE,
    DiscordOAuth,
    DiscordOAuthError,
    DiscordToken,
    DiscordUser,
)

CLIENT_ID = "client-id"
CLIENT_SECRET = "client-secret"
REDIRECT_URI = "https://example.com/callback"


def build_oauth(http: ClientSession) -> DiscordOAuth:
    return DiscordOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        http=http,
    )


@pytest.mark.asyncio
async def test_authorization_url_contains_required_params():
    async with ClientSession() as http:
        oauth = build_oauth(http=http)
        url = oauth.authorization_url(
            redirect_uri=REDIRECT_URI,
            state="csrf-state",
        )

    parsed = urlparse(url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "discord.com"
    assert parsed.path == "/oauth2/authorize"
    query = parse_qs(parsed.query)
    assert query["response_type"] == ["code"]
    assert query["client_id"] == [CLIENT_ID]
    assert query["scope"] == ["identify"]
    assert query["redirect_uri"] == [REDIRECT_URI]
    assert query["state"] == ["csrf-state"]


@pytest.mark.asyncio
async def test_exchange_code_returns_token():
    payload = {
        "access_token": "an-access-token",
        "token_type": "Bearer",
        "expires_in": 604800,
        "refresh_token": "a-refresh-token",
        "scope": "identify",
    }

    async with ClientSession() as http:
        oauth = build_oauth(http=http)
        with aioresponses() as mocked:
            mocked.post(f"{DISCORD_API_BASE}/oauth2/token", payload=payload)
            token = await oauth.exchange_code(code="a-code", redirect_uri=REDIRECT_URI)

    assert token == DiscordToken.model_validate(payload)


@pytest.mark.asyncio
async def test_exchange_code_returns_error_on_http_error():
    async with ClientSession() as http:
        oauth = build_oauth(http=http)
        with aioresponses() as mocked:
            mocked.post(
                f"{DISCORD_API_BASE}/oauth2/token",
                status=400,
                payload={"error": "invalid_grant"},
            )
            result = await oauth.exchange_code(
                code="bad-code", redirect_uri=REDIRECT_URI
            )

    assert isinstance(result, DiscordOAuthError)


@pytest.mark.asyncio
async def test_get_current_user_returns_user():
    payload = {"id": "268473310986240001", "username": "discord"}

    async with ClientSession() as http:
        oauth = build_oauth(http=http)
        with aioresponses() as mocked:
            mocked.get(f"{DISCORD_API_BASE}/users/@me", payload=payload)
            user = await oauth.get_current_user(access_token="an-access-token")

    assert user == DiscordUser.model_validate(payload)


@pytest.mark.asyncio
async def test_refresh_token_returns_token():
    payload = {
        "access_token": "a-new-access-token",
        "token_type": "Bearer",
        "expires_in": 604800,
        "refresh_token": "a-new-refresh-token",
        "scope": "identify",
    }

    async with ClientSession() as http:
        oauth = build_oauth(http=http)
        with aioresponses() as mocked:
            mocked.post(f"{DISCORD_API_BASE}/oauth2/token", payload=payload)
            token = await oauth.refresh_token(refresh_token="a-refresh-token")

    assert token == DiscordToken.model_validate(payload)
