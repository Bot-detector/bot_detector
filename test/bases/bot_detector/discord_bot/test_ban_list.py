import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("DISCORD_TOKEN", "test-token")
os.environ.setdefault("OSRS_ITEMS_USER_AGENT", "test-agent")

from bot_detector.discord_bot.cogs.bot_detective_commands import (
    botDetectiveCommands,
)


async def _invoke_ban_list(cog: botDetectiveCommands, ctx: AsyncMock, url: str):
    return await type(cog).ban_list.callback(cog, ctx, url)


def _make_cog() -> botDetectiveCommands:
    bot = MagicMock()
    deps = MagicMock()
    deps.session = AsyncMock()
    deps.legacy_api = AsyncMock()
    return botDetectiveCommands(bot=bot, deps=deps)


def _make_player(name: str, label_jagex: int | None = None) -> dict:
    return {"name": name, "label_jagex": label_jagex}


def _make_ctx(*, reply_raises: Exception | None = None) -> AsyncMock:
    ctx = AsyncMock()
    ctx.author.name = "test_user"
    ctx.author.id = 12345
    if reply_raises:
        ctx.reply.side_effect = reply_raises
    return ctx


def _read_file_content(discord_file) -> str:
    discord_file.fp.seek(0)
    return discord_file.fp.read().decode()


PASTEBIN_URL = "https://pastebin.com/abc123"


@pytest.mark.asyncio
async def test_ban_list_partitions_banned_and_not_banned():
    cog = _make_cog()
    ctx = _make_ctx()

    cog._get_pastebin = AsyncMock(return_value="bot1\r\nlegit1")
    cog._parse_pastebin = AsyncMock(return_value=["bot1", "legit1"])
    cog.deps.legacy_api.get_player = AsyncMock(
        side_effect=[
            _make_player("bot1", label_jagex=2),
            _make_player("legit1", label_jagex=1),
        ]
    )

    with patch(
        "bot_detector.discord_bot.cogs.bot_detective_commands.time"
    ) as mock_time:
        mock_time.time.return_value = 1715788800
        await _invoke_ban_list(cog, ctx, PASTEBIN_URL)

    ctx.reply.assert_awaited_once()
    call_kwargs = ctx.reply.call_args.kwargs
    embed = call_kwargs["embed"]
    files = call_kwargs["files"]

    assert embed.title == "Ban List"
    assert len(files) == 2

    banned_file = next(f for f in files if f.filename == "1715788800_banned.txt")
    not_banned_file = next(
        f for f in files if f.filename == "1715788800_not_banned.txt"
    )

    assert _read_file_content(banned_file) == "bot1"
    assert _read_file_content(not_banned_file) == "legit1"


@pytest.mark.asyncio
async def test_ban_list_summary_embed_counts():
    cog = _make_cog()
    ctx = _make_ctx()

    players = [
        _make_player("b1", label_jagex=2),
        _make_player("b2", label_jagex=2),
        _make_player("s1", label_jagex=1),
    ]

    cog._get_pastebin = AsyncMock(return_value="b1\r\nb2\r\ns1")
    cog._parse_pastebin = AsyncMock(return_value=["b1", "b2", "s1"])
    cog.deps.legacy_api.get_player = AsyncMock(side_effect=players)

    with patch(
        "bot_detector.discord_bot.cogs.bot_detective_commands.time"
    ) as mock_time:
        mock_time.time.return_value = 1715788800
        await _invoke_ban_list(cog, ctx, PASTEBIN_URL)

    embed = ctx.reply.call_args.kwargs["embed"]
    fields = {f.name: f.value for f in embed.fields}
    assert fields["Total"] == "3"
    assert fields["Banned"] == "2"
    assert fields["Not Banned"] == "1"


@pytest.mark.asyncio
async def test_ban_list_empty_banned_sends_empty_file():
    cog = _make_cog()
    ctx = _make_ctx()

    players = [
        _make_player("s1", label_jagex=1),
        _make_player("s2", label_jagex=0),
    ]

    cog._get_pastebin = AsyncMock(return_value="s1\r\ns2")
    cog._parse_pastebin = AsyncMock(return_value=["s1", "s2"])
    cog.deps.legacy_api.get_player = AsyncMock(side_effect=players)

    with patch(
        "bot_detector.discord_bot.cogs.bot_detective_commands.time"
    ) as mock_time:
        mock_time.time.return_value = 1715788800
        await _invoke_ban_list(cog, ctx, PASTEBIN_URL)

    files = ctx.reply.call_args.kwargs["files"]
    banned_file = next(f for f in files if "banned" in f.filename)
    assert _read_file_content(banned_file) == ""


@pytest.mark.asyncio
async def test_ban_list_empty_not_banned_sends_empty_file():
    cog = _make_cog()
    ctx = _make_ctx()

    players = [
        _make_player("b1", label_jagex=2),
        _make_player("b2", label_jagex=2),
    ]

    cog._get_pastebin = AsyncMock(return_value="b1\r\nb2")
    cog._parse_pastebin = AsyncMock(return_value=["b1", "b2"])
    cog.deps.legacy_api.get_player = AsyncMock(side_effect=players)

    with patch(
        "bot_detector.discord_bot.cogs.bot_detective_commands.time"
    ) as mock_time:
        mock_time.time.return_value = 1715788800
        await _invoke_ban_list(cog, ctx, PASTEBIN_URL)

    files = ctx.reply.call_args.kwargs["files"]
    not_banned_file = next(f for f in files if "not_banned" in f.filename)
    assert _read_file_content(not_banned_file) == ""


@pytest.mark.asyncio
async def test_ban_list_no_valid_players_sends_message():
    cog = _make_cog()
    ctx = _make_ctx()

    cog._get_pastebin = AsyncMock(return_value="player1")
    cog._parse_pastebin = AsyncMock(return_value=["player1"])
    cog.deps.legacy_api.get_player = AsyncMock(return_value=None)

    await _invoke_ban_list(cog, ctx, PASTEBIN_URL)

    ctx.reply.assert_awaited_once_with("No valid players found.")


@pytest.mark.asyncio
async def test_ban_list_invalid_url_returns_early():
    cog = _make_cog()
    ctx = _make_ctx()

    await _invoke_ban_list(cog, ctx, "https://example.com/not-pastebin")

    ctx.reply.assert_awaited_once_with("Please submit a pastebin url.")


@pytest.mark.asyncio
async def test_ban_list_pastebin_fetch_failure():
    cog = _make_cog()
    ctx = _make_ctx()

    cog._get_pastebin = AsyncMock(return_value=None)

    await _invoke_ban_list(cog, ctx, PASTEBIN_URL)

    ctx.reply.assert_awaited_once_with("could not get pastebin")


@pytest.mark.asyncio
async def test_ban_list_file_naming_uses_epoch():
    cog = _make_cog()
    ctx = _make_ctx()

    cog._get_pastebin = AsyncMock(return_value="p1")
    cog._parse_pastebin = AsyncMock(return_value=["p1"])
    cog.deps.legacy_api.get_player = AsyncMock(
        return_value=_make_player("p1", label_jagex=2)
    )

    with patch(
        "bot_detector.discord_bot.cogs.bot_detective_commands.time"
    ) as mock_time:
        mock_time.time.return_value = 1747354800
        await _invoke_ban_list(cog, ctx, PASTEBIN_URL)

    files = ctx.reply.call_args.kwargs["files"]
    filenames = [f.filename for f in files]
    assert "1747354800_banned.txt" in filenames
    assert "1747354800_not_banned.txt" in filenames


@pytest.mark.asyncio
async def test_ban_list_cleans_up_temp_dir():
    cog = _make_cog()
    ctx = _make_ctx()

    cog._get_pastebin = AsyncMock(return_value="p1")
    cog._parse_pastebin = AsyncMock(return_value=["p1"])
    cog.deps.legacy_api.get_player = AsyncMock(
        return_value=_make_player("p1", label_jagex=2)
    )

    created_dirs: list[str] = []
    original_mkdtemp = tempfile.mkdtemp

    def tracking_mkdtemp():
        d = original_mkdtemp()
        created_dirs.append(d)
        return d

    with (
        patch(
            "bot_detector.discord_bot.cogs.bot_detective_commands.tempfile.mkdtemp",
            side_effect=tracking_mkdtemp,
        ),
        patch("bot_detector.discord_bot.cogs.bot_detective_commands.time") as mock_time,
    ):
        mock_time.time.return_value = 1715788800
        await _invoke_ban_list(cog, ctx, PASTEBIN_URL)

    assert len(created_dirs) == 1
    assert not Path(created_dirs[0]).exists()


@pytest.mark.asyncio
async def test_ban_list_cleans_up_even_if_reply_raises():
    cog = _make_cog()
    ctx = _make_ctx(reply_raises=RuntimeError("discord error"))

    cog._get_pastebin = AsyncMock(return_value="p1")
    cog._parse_pastebin = AsyncMock(return_value=["p1"])
    cog.deps.legacy_api.get_player = AsyncMock(
        return_value=_make_player("p1", label_jagex=2)
    )

    created_dirs: list[str] = []
    original_mkdtemp = tempfile.mkdtemp

    def tracking_mkdtemp():
        d = original_mkdtemp()
        created_dirs.append(d)
        return d

    with (
        patch(
            "bot_detector.discord_bot.cogs.bot_detective_commands.tempfile.mkdtemp",
            side_effect=tracking_mkdtemp,
        ),
        patch("bot_detector.discord_bot.cogs.bot_detective_commands.time") as mock_time,
        pytest.raises(RuntimeError),
    ):
        mock_time.time.return_value = 1715788800
        await _invoke_ban_list(cog, ctx, PASTEBIN_URL)

    assert len(created_dirs) == 1
    assert not Path(created_dirs[0]).exists()


@pytest.mark.asyncio
async def test_ban_list_file_content_one_name_per_line():
    cog = _make_cog()
    ctx = _make_ctx()

    players = [
        _make_player("bot_a", label_jagex=2),
        _make_player("bot_b", label_jagex=2),
        _make_player("legit_c", label_jagex=1),
        _make_player("legit_d", label_jagex=0),
    ]

    cog._get_pastebin = AsyncMock(return_value="names")
    cog._parse_pastebin = AsyncMock(
        return_value=["bot_a", "bot_b", "legit_c", "legit_d"]
    )
    cog.deps.legacy_api.get_player = AsyncMock(side_effect=players)

    with patch(
        "bot_detector.discord_bot.cogs.bot_detective_commands.time"
    ) as mock_time:
        mock_time.time.return_value = 1715788800
        await _invoke_ban_list(cog, ctx, PASTEBIN_URL)

    files = ctx.reply.call_args.kwargs["files"]
    banned_file = next(
        f for f in files if "banned.txt" in f.filename and "not" not in f.filename
    )
    not_banned_file = next(f for f in files if "not_banned" in f.filename)

    assert _read_file_content(banned_file).split("\n") == ["bot_a", "bot_b"]
    assert _read_file_content(not_banned_file).split("\n") == ["legit_c", "legit_d"]


@pytest.mark.asyncio
async def test_ban_list_player_without_name_uses_unknown():
    cog = _make_cog()
    ctx = _make_ctx()

    players = [
        {"label_jagex": 2},
    ]

    cog._get_pastebin = AsyncMock(return_value="p1")
    cog._parse_pastebin = AsyncMock(return_value=["p1"])
    cog.deps.legacy_api.get_player = AsyncMock(side_effect=players)

    with patch(
        "bot_detector.discord_bot.cogs.bot_detective_commands.time"
    ) as mock_time:
        mock_time.time.return_value = 1715788800
        await _invoke_ban_list(cog, ctx, PASTEBIN_URL)

    files = ctx.reply.call_args.kwargs["files"]
    banned_file = next(
        f for f in files if "banned.txt" in f.filename and "not" not in f.filename
    )
    assert _read_file_content(banned_file) == "unknown"
