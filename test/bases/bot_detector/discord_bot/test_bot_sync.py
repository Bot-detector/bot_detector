import os
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

os.environ.setdefault("DISCORD_TOKEN", "test-token")
os.environ.setdefault("OSRS_ITEMS_USER_AGENT", "test-agent")

from bot_detector.discord_bot.bot import sync as sync_command


def _make_ctx() -> AsyncMock:
    ctx = AsyncMock()
    ctx.author.name = "test_user"
    ctx.author.id = 12345
    ctx.guild = MagicMock()
    ctx.bot.tree.sync = AsyncMock(return_value=[MagicMock(), MagicMock()])
    ctx.bot.tree.copy_global_to = MagicMock()
    ctx.bot.tree.clear_commands = MagicMock()
    return ctx


@pytest.mark.asyncio
async def test_sync_global_by_default():
    ctx = _make_ctx()

    await sync_command.callback(ctx, spec=None, guild_id=None)

    ctx.bot.tree.sync.assert_awaited_once_with()
    ctx.send.assert_awaited_once_with("Synced 2 commands globally")


@pytest.mark.asyncio
async def test_sync_current_guild_with_tilde():
    ctx = _make_ctx()

    await sync_command.callback(ctx, spec="~", guild_id=None)

    ctx.bot.tree.sync.assert_awaited_once_with(guild=ctx.guild)
    ctx.send.assert_awaited_once_with("Synced 2 commands to the current guild.")


@pytest.mark.asyncio
async def test_sync_copies_global_to_guild_with_star():
    ctx = _make_ctx()

    await sync_command.callback(ctx, spec="*", guild_id=None)

    ctx.bot.tree.copy_global_to.assert_called_once_with(guild=ctx.guild)
    ctx.bot.tree.sync.assert_awaited_once_with(guild=ctx.guild)


@pytest.mark.asyncio
async def test_sync_clears_guild_with_caret():
    ctx = _make_ctx()

    await sync_command.callback(ctx, spec="^", guild_id=None)

    ctx.bot.tree.clear_commands.assert_called_once_with(guild=ctx.guild)
    ctx.bot.tree.sync.assert_awaited_once_with(guild=ctx.guild)
    ctx.send.assert_awaited_once_with("Synced 0 commands to the current guild.")


@pytest.mark.asyncio
async def test_sync_specific_guild_by_id():
    ctx = _make_ctx()

    await sync_command.callback(ctx, spec=None, guild_id=987654321)

    ctx.bot.tree.sync.assert_awaited_once_with(guild=discord.Object(id=987654321))
    ctx.send.assert_awaited_once_with("Synced the tree to guild 987654321.")
