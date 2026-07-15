import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

os.environ.setdefault("DISCORD_TOKEN", "test-token")
os.environ.setdefault("OSRS_ITEMS_USER_AGENT", "test-agent")

from bot_detector.discord_bot.cogs.error_handler import errorHandler


def _make_cog() -> errorHandler:
    bot = MagicMock()
    deps = MagicMock()
    return errorHandler(bot=bot, deps=deps)


def _make_ctx() -> AsyncMock:
    ctx = AsyncMock()
    ctx.author.name = "test_user"
    ctx.author.id = 12345
    ctx.command = SimpleNamespace()
    ctx.cog = None
    ctx.message = MagicMock()
    ctx.message.jump_url = "http://discord.com/jump/123"
    ctx.interaction = None
    return ctx


def _make_http_exception(status: int = 500) -> discord.HTTPException:
    response = MagicMock()
    response.status = status
    response.headers = {}
    return discord.HTTPException(response=response, message="test error")


@pytest.mark.asyncio
async def test_ratelimited_responds_with_retry_after():
    cog = _make_cog()
    ctx = _make_ctx()

    error = discord.RateLimited(retry_after=120.0)

    await cog.on_command_error(ctx, error)

    ctx.send.assert_awaited_once()
    msg = ctx.send.call_args.args[0]
    assert "120s" in msg


@pytest.mark.asyncio
async def test_ratelimited_does_not_trigger_webhook():
    cog = _make_cog()
    ctx = _make_ctx()

    error = discord.RateLimited(retry_after=60.0)

    with patch.object(
        cog, "_send_error_webhook", new_callable=AsyncMock
    ) as mock_webhook:
        await cog.on_command_error(ctx, error)

    mock_webhook.assert_not_awaited()


@pytest.mark.asyncio
async def test_http_exception_triggers_webhook():
    cog = _make_cog()
    ctx = _make_ctx()

    error = _make_http_exception(status=500)

    with patch.object(
        cog, "_send_error_webhook", new_callable=AsyncMock
    ) as mock_webhook:
        await cog.on_command_error(ctx, error)

    mock_webhook.assert_awaited_once()


@pytest.mark.asyncio
async def test_safe_respond_uses_interaction_followup():
    """When interaction is done, should use interaction.followup.send."""
    cog = _make_cog()
    ctx = _make_ctx()
    ctx.interaction = MagicMock()
    ctx.interaction.response.is_done.return_value = True
    ctx.interaction.followup = AsyncMock()

    await cog._safe_respond(ctx, "test message")

    ctx.interaction.followup.send.assert_awaited_once_with(
        "test message", ephemeral=True
    )
    ctx.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_safe_respond_uses_ctx_send_when_no_interaction():
    """When no interaction, should fall back to ctx.send."""
    cog = _make_cog()
    ctx = _make_ctx()

    await cog._safe_respond(ctx, "test message")

    ctx.send.assert_awaited_once_with("test message")


@pytest.mark.asyncio
async def test_safe_respond_swallows_send_failure():
    cog = _make_cog()
    ctx = _make_ctx()
    ctx.send.side_effect = discord.HTTPException(
        response=MagicMock(status=404, headers={}), message="not found"
    )

    await cog._safe_respond(ctx, "test message")
