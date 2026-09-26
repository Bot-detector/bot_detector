import asyncio

import pytest
from aiohttp import ClientError, ClientSession
from aioresponses import aioresponses
from bot_detector.firehose.app.auth.discord import (
    DISCORD_API_BASE,
    DiscordOAuth,
    DiscordOAuthError,
    DiscordUser,
)


def build_oauth(http: ClientSession) -> DiscordOAuth:
    return DiscordOAuth(http=http)


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
async def test_get_current_user_returns_error_on_http_error():
    async with ClientSession() as http:
        oauth = build_oauth(http=http)
        with aioresponses() as mocked:
            mocked.get(
                f"{DISCORD_API_BASE}/users/@me",
                status=401,
                payload={"message": "401: Unauthorized", "code": 0},
            )
            user = await oauth.get_current_user(access_token="a-bad-token")

    assert isinstance(user, DiscordOAuthError)


@pytest.mark.asyncio
async def test_get_current_user_returns_error_on_timeout():
    async with ClientSession() as http:
        oauth = build_oauth(http=http)
        with aioresponses() as mocked:
            mocked.get(
                f"{DISCORD_API_BASE}/users/@me",
                exception=asyncio.TimeoutError(),
            )
            user = await oauth.get_current_user(access_token="an-access-token")

    assert isinstance(user, DiscordOAuthError)


@pytest.mark.asyncio
async def test_get_current_user_returns_error_on_client_error():
    async with ClientSession() as http:
        oauth = build_oauth(http=http)
        with aioresponses() as mocked:
            mocked.get(
                f"{DISCORD_API_BASE}/users/@me",
                exception=ClientError("connection reset"),
            )
            user = await oauth.get_current_user(access_token="an-access-token")

    assert isinstance(user, DiscordOAuthError)
