import asyncio
import socket

import pytest
from aiohttp import ClientSession, ClientTimeout, web
from aiohttp.test_utils import TestServer
from bot_detector.firehose.app.auth import discord as discord_module
from bot_detector.firehose.app.auth.discord import (
    DiscordOAuth,
    DiscordOAuthError,
    DiscordUser,
)


def build_oauth(http: ClientSession) -> DiscordOAuth:
    return DiscordOAuth(http=http)


@pytest.mark.asyncio
async def test_get_current_user_returns_user(monkeypatch: pytest.MonkeyPatch):
    payload = {"id": "268473310986240001", "username": "discord"}

    async def user(request: web.Request) -> web.Response:
        return web.json_response(payload)

    app = web.Application()
    app.router.add_get("/users/@me", user)
    server = TestServer(app)
    await server.start_server()
    monkeypatch.setattr(discord_module, "DISCORD_API_BASE", str(server.make_url("")))
    try:
        async with ClientSession() as http:
            oauth = build_oauth(http=http)
            user_result = await oauth.get_current_user(access_token="an-access-token")
    finally:
        await server.close()

    assert user_result == DiscordUser.model_validate(payload)


@pytest.mark.asyncio
async def test_get_current_user_returns_error_on_http_error(
    monkeypatch: pytest.MonkeyPatch,
):
    async def user(request: web.Request) -> web.Response:
        return web.json_response(
            {"message": "401: Unauthorized", "code": 0},
            status=401,
        )

    app = web.Application()
    app.router.add_get("/users/@me", user)
    server = TestServer(app)
    await server.start_server()
    monkeypatch.setattr(discord_module, "DISCORD_API_BASE", str(server.make_url("")))
    try:
        async with ClientSession() as http:
            oauth = build_oauth(http=http)
            user_result = await oauth.get_current_user(access_token="a-bad-token")
    finally:
        await server.close()

    assert isinstance(user_result, DiscordOAuthError)


@pytest.mark.asyncio
async def test_get_current_user_returns_error_on_timeout(
    monkeypatch: pytest.MonkeyPatch,
):
    async def user(request: web.Request) -> web.Response:
        # only needs to outlast the client's 0.05s total timeout: the
        # timeout path fires while this handler is still parked
        await asyncio.sleep(0.2)
        return web.json_response({})

    app = web.Application()
    app.router.add_get("/users/@me", user)
    server = TestServer(app)
    await server.start_server()
    monkeypatch.setattr(discord_module, "DISCORD_API_BASE", str(server.make_url("")))
    try:
        async with ClientSession(timeout=ClientTimeout(total=0.05)) as http:
            oauth = build_oauth(http=http)
            user_result = await oauth.get_current_user(access_token="an-access-token")
    finally:
        await server.close()

    assert isinstance(user_result, DiscordOAuthError)


def closed_port() -> int:
    """An ephemeral port with no listener: connect is refused at once.

    Hard-coding a privileged port hangs behind firewalls that DROP
    instead of REJECT (10s client timeout); a fresh bind-then-close
    socket fails with a connection-level ClientError everywhere.
    """
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.asyncio
async def test_get_current_user_returns_error_on_client_error(
    monkeypatch: pytest.MonkeyPatch,
):
    # point at a port with no listener: connection-level ClientError
    monkeypatch.setattr(
        discord_module, "DISCORD_API_BASE", f"http://127.0.0.1:{closed_port()}"
    )
    async with ClientSession() as http:
        oauth = build_oauth(http=http)
        user_result = await oauth.get_current_user(access_token="an-access-token")

    assert isinstance(user_result, DiscordOAuthError)
