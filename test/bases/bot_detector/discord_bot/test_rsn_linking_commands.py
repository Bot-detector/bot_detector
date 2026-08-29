import os
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

os.environ.setdefault("DISCORD_TOKEN", "test-token")
os.environ.setdefault("OSRS_ITEMS_USER_AGENT", "test-agent")

from bot_detector.discord_bot.cogs.rsn_linking_commands import rsnLinkingCommands
from bot_detector.discord_bot.utils import checks

VERIFIED_ROLE_ID = checks.VERIFIED_PLAYER_ROLE


def _make_cog() -> rsnLinkingCommands:
    bot = MagicMock()
    deps = MagicMock()
    deps.legacy_api = AsyncMock()
    cog = rsnLinkingCommands(bot=bot, deps=deps)
    cog.verification_repo = AsyncMock()
    return cog


def _make_ctx(*, guild: bool = False, member: bool = False) -> AsyncMock:
    ctx = AsyncMock()
    ctx.author.name = "test_user"
    ctx.author.id = 12345
    ctx.command = MagicMock()
    if guild:
        ctx.guild = MagicMock()
        ctx.guild.roles = []
    else:
        ctx.guild = None
    if member:
        member_mock = MagicMock(spec=discord.Member)
        member_mock.name = "test_user"
        member_mock.id = 12345
        ctx.author = member_mock
    return ctx


def _make_session_factory() -> MagicMock:
    session = AsyncMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)
    factory = MagicMock(return_value=cm)
    return factory


async def _invoke(cog: rsnLinkingCommands, ctx: AsyncMock, name: str):
    return await type(cog).unlink.callback(cog, ctx, name=name)


async def _invoke_set_primary(cog: rsnLinkingCommands, ctx: AsyncMock, name: str):
    return await type(cog).set_primary.callback(cog, ctx, name=name)


def _verified_role() -> MagicMock:
    role = MagicMock(spec=discord.Role)
    role.id = VERIFIED_ROLE_ID
    return role


@pytest.mark.asyncio
async def test_unlink_success_replies_embed():
    cog = _make_cog()
    ctx = _make_ctx()

    cog.deps.legacy_api.get_player = AsyncMock(
        return_value={"id": 42, "name": "Zezima"}
    )
    cog.deps.get_session_factory = MagicMock(return_value=_make_session_factory())
    cog.verification_repo.delete_verification = AsyncMock(return_value=True)
    cog.verification_repo.get_linked_accounts = AsyncMock(return_value=[])

    await _invoke(cog, ctx, "Zezima")

    ctx.reply.assert_awaited_once()
    embed = ctx.reply.call_args.kwargs["embed"]
    assert embed.title == "Unlinking 'Zezima':"
    fields = {f.name for f in embed.fields}
    assert "STATUS" in fields
    assert "ROLES" not in fields


@pytest.mark.asyncio
async def test_unlink_invalid_rsn_rejected():
    cog = _make_cog()
    ctx = _make_ctx()

    await _invoke(cog, ctx, "this name is way too long")

    ctx.reply.assert_awaited_once_with(
        "this name is way too long isn't a valid Runescape user name."
    )
    cog.deps.legacy_api.get_player.assert_not_called()


@pytest.mark.asyncio
async def test_unlink_player_not_found():
    cog = _make_cog()
    ctx = _make_ctx()

    cog.deps.legacy_api.get_player = AsyncMock(return_value=None)

    await _invoke(cog, ctx, "Zezima")

    ctx.reply.assert_awaited_once_with(
        "No player found for 'Zezima'. Nothing to unlink."
    )
    cog.verification_repo.delete_verification.assert_not_called()


@pytest.mark.asyncio
async def test_unlink_not_linked_rejected():
    cog = _make_cog()
    ctx = _make_ctx()

    cog.deps.legacy_api.get_player = AsyncMock(
        return_value={"id": 42, "name": "Zezima"}
    )
    cog.deps.get_session_factory = MagicMock(return_value=_make_session_factory())
    cog.verification_repo.delete_verification = AsyncMock(return_value=False)
    cog.verification_repo.get_linked_accounts = AsyncMock()

    await _invoke(cog, ctx, "Zezima")

    ctx.reply.assert_awaited_once_with(
        "'Zezima' is not linked to your Discord account."
    )
    cog.verification_repo.get_linked_accounts.assert_not_called()


@pytest.mark.asyncio
async def test_unlink_removes_verified_role_when_none_remaining():
    cog = _make_cog()
    ctx = _make_ctx(guild=True, member=True)
    role = _verified_role()
    ctx.guild.roles = [role]
    ctx.author.roles = [role]
    ctx.author.id = 12345

    cog.deps.legacy_api.get_player = AsyncMock(
        return_value={"id": 42, "name": "Zezima"}
    )
    cog.deps.get_session_factory = MagicMock(return_value=_make_session_factory())
    cog.verification_repo.delete_verification = AsyncMock(return_value=True)
    cog.verification_repo.get_linked_accounts = AsyncMock(return_value=[])

    await _invoke(cog, ctx, "Zezima")

    ctx.author.remove_roles.assert_awaited_once_with(role)
    embed = ctx.reply.call_args.kwargs["embed"]
    fields = {f.name for f in embed.fields}
    assert "ROLES" in fields


@pytest.mark.asyncio
async def test_unlink_keeps_role_when_verified_accounts_remain():
    cog = _make_cog()
    ctx = _make_ctx(guild=True, member=True)
    role = _verified_role()
    ctx.guild.roles = [role]
    ctx.author.roles = [role]
    ctx.author.id = 12345

    cog.deps.legacy_api.get_player = AsyncMock(
        return_value={"id": 42, "name": "Zezima"}
    )
    cog.deps.get_session_factory = MagicMock(return_value=_make_session_factory())
    cog.verification_repo.delete_verification = AsyncMock(return_value=True)
    cog.verification_repo.get_linked_accounts = AsyncMock(return_value=[MagicMock()])

    await _invoke(cog, ctx, "Zezima")

    ctx.author.remove_roles.assert_not_awaited()
    embed = ctx.reply.call_args.kwargs["embed"]
    fields = {f.name for f in embed.fields}
    assert "ROLES" not in fields


@pytest.mark.asyncio
async def test_unlink_skips_role_lookup_outside_guild():
    cog = _make_cog()
    ctx = _make_ctx(guild=False)

    cog.deps.legacy_api.get_player = AsyncMock(
        return_value={"id": 42, "name": "Zezima"}
    )
    cog.deps.get_session_factory = MagicMock(return_value=_make_session_factory())
    cog.verification_repo.delete_verification = AsyncMock(return_value=True)
    cog.verification_repo.get_linked_accounts = AsyncMock(return_value=[])

    await _invoke(cog, ctx, "Zezima")

    cog.verification_repo.get_linked_accounts.assert_awaited_once()
    ctx.author.remove_roles.assert_not_awaited()


def _linked_account(player_id: int, primary_rsn: int = 0) -> MagicMock:
    account = MagicMock()
    account.Player_id = player_id
    account.primary_rsn = primary_rsn
    return account


@pytest.mark.asyncio
async def test_set_primary_success_replies_embed():
    cog = _make_cog()
    ctx = _make_ctx()

    cog.deps.legacy_api.get_player = AsyncMock(
        return_value={"id": 42, "name": "Zezima"}
    )
    cog.deps.get_session_factory = MagicMock(return_value=_make_session_factory())
    cog.verification_repo.get_linked_accounts = AsyncMock(
        return_value=[_linked_account(player_id=42)]
    )
    cog.verification_repo.set_primary_rsn = AsyncMock(return_value=True)

    await _invoke_set_primary(cog, ctx, "Zezima")

    cog.verification_repo.set_primary_rsn.assert_awaited_once()
    kwargs = cog.verification_repo.set_primary_rsn.call_args.kwargs
    assert kwargs["discord_id"] == "12345"
    assert kwargs["player_id"] == 42
    assert kwargs["is_primary"] is True
    ctx.reply.assert_awaited_once()
    embed = ctx.reply.call_args.kwargs["embed"]
    assert embed.title == "Setting 'Zezima' as Primary:"
    fields = {f.name for f in embed.fields}
    assert "STATUS" in fields


@pytest.mark.asyncio
async def test_set_primary_invalid_rsn_rejected():
    cog = _make_cog()
    ctx = _make_ctx()

    await _invoke_set_primary(cog, ctx, "this name is way too long")

    ctx.reply.assert_awaited_once_with(
        "this name is way too long isn't a valid Runescape user name."
    )
    cog.deps.legacy_api.get_player.assert_not_called()


@pytest.mark.asyncio
async def test_set_primary_player_not_found():
    cog = _make_cog()
    ctx = _make_ctx()

    cog.deps.legacy_api.get_player = AsyncMock(return_value=None)

    await _invoke_set_primary(cog, ctx, "Zezima")

    ctx.reply.assert_awaited_once_with("No player found for 'Zezima'.")
    cog.verification_repo.set_primary_rsn.assert_not_called()


@pytest.mark.asyncio
async def test_set_primary_not_linked_rejected():
    cog = _make_cog()
    ctx = _make_ctx()

    cog.deps.legacy_api.get_player = AsyncMock(
        return_value={"id": 42, "name": "Zezima"}
    )
    cog.deps.get_session_factory = MagicMock(return_value=_make_session_factory())
    cog.verification_repo.get_linked_accounts = AsyncMock(
        return_value=[_linked_account(player_id=7)]
    )

    await _invoke_set_primary(cog, ctx, "Zezima")

    ctx.reply.assert_awaited_once_with(
        "'Zezima' is not linked to your Discord account."
    )
    cog.verification_repo.set_primary_rsn.assert_not_called()


@pytest.mark.asyncio
async def test_set_primary_already_primary_rejected():
    cog = _make_cog()
    ctx = _make_ctx()

    cog.deps.legacy_api.get_player = AsyncMock(
        return_value={"id": 42, "name": "Zezima"}
    )
    cog.deps.get_session_factory = MagicMock(return_value=_make_session_factory())
    cog.verification_repo.get_linked_accounts = AsyncMock(
        return_value=[_linked_account(player_id=42, primary_rsn=1)]
    )

    await _invoke_set_primary(cog, ctx, "Zezima")

    ctx.reply.assert_awaited_once_with("'Zezima' is already your primary account.")
    cog.verification_repo.set_primary_rsn.assert_not_called()


@pytest.mark.asyncio
async def test_set_primary_update_failure_replies_error():
    cog = _make_cog()
    ctx = _make_ctx()

    cog.deps.legacy_api.get_player = AsyncMock(
        return_value={"id": 42, "name": "Zezima"}
    )
    cog.deps.get_session_factory = MagicMock(return_value=_make_session_factory())
    cog.verification_repo.get_linked_accounts = AsyncMock(
        return_value=[_linked_account(player_id=42)]
    )
    cog.verification_repo.set_primary_rsn = AsyncMock(return_value=False)

    await _invoke_set_primary(cog, ctx, "Zezima")

    ctx.reply.assert_awaited_once_with(
        "Failed to set 'Zezima' as your primary account."
    )
