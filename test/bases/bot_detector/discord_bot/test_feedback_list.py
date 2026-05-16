import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("DISCORD_TOKEN", "test-token")
os.environ.setdefault("OSRS_ITEMS_USER_AGENT", "test-agent")

from bot_detector.discord_bot.cogs.feedback_list_commands import (
    _build_csv,
    _safe_slug,
    _split_feedback,
    feedbackListCommands,
)
from bot_detector.structs.feedback import FeedbackExportItem, FeedbackExportResponse


def _make_cog() -> feedbackListCommands:
    bot = MagicMock()
    deps = MagicMock()
    deps.session = AsyncMock()
    deps.legacy_api = AsyncMock()
    deps.public_api = AsyncMock()
    return feedbackListCommands(bot=bot, deps=deps)


def _make_ctx(*, reply_raises: Exception | None = None) -> AsyncMock:
    ctx = AsyncMock()
    ctx.author.name = "test_user"
    ctx.author.id = 12345
    if reply_raises:
        ctx.reply.side_effect = reply_raises
    return ctx


async def _invoke(cog: feedbackListCommands, ctx: AsyncMock, player_name: str):
    return await type(cog).feedback_list.callback(cog, ctx, player_name=player_name)


def _make_item(
    subject_name: str = "target",
    is_banned: bool = False,
    vote: int = -1,
    prediction: str = "Bot",
) -> FeedbackExportItem:
    return FeedbackExportItem(
        subject_name=subject_name,
        is_banned=is_banned,
        vote=vote,
        prediction=prediction,
    )


def _make_response(
    items: list[FeedbackExportItem], player_name: str = "zezima"
) -> FeedbackExportResponse:
    return FeedbackExportResponse(
        player_name=player_name,
        total_feedback=len(items),
        feedback=items,
    )


def _read_file_content(discord_file) -> str:
    discord_file.fp.seek(0)
    return discord_file.fp.read().decode()


def _linked_account(name: str, verified: bool = True) -> dict:
    return {"name": name, "Verified_status": 1 if verified else 0}


@pytest.mark.asyncio
async def test_success_sends_three_csvs_and_embed():
    cog = _make_cog()
    ctx = _make_ctx()

    cog.deps.legacy_api.get_discord_links = AsyncMock(
        return_value=[_linked_account("Zezima")]
    )
    items = [
        _make_item("bot1", is_banned=True, vote=-1, prediction="Bot"),
        _make_item("legit1", is_banned=False, vote=0, prediction="Bot"),
        _make_item("real1", is_banned=False, vote=1, prediction="Real_Player"),
    ]
    cog.deps.public_api.get_feedback_export = AsyncMock(
        return_value=_make_response(items)
    )

    with patch(
        "bot_detector.discord_bot.cogs.feedback_list_commands.time"
    ) as mock_time:
        mock_time.time.return_value = 1715788800.0
        await _invoke(cog, ctx, "Zezima")

    ctx.reply.assert_awaited_once()
    call_kwargs = ctx.reply.call_args.kwargs
    embed = call_kwargs["embed"]
    files = call_kwargs["files"]

    assert embed.title == "Feedback Export"
    assert len(files) == 3

    filenames = [f.filename for f in files]
    assert "1715788800_zezima_banned.csv" in filenames
    assert "1715788800_zezima_not_banned.csv" in filenames
    assert "1715788800_zezima_flagged_real_player.csv" in filenames

    fields = {f.name: f.value for f in embed.fields}
    assert fields["Total Feedback"] == "3"
    assert fields["Banned"] == "1"
    assert fields["Not Banned"] == "2"
    assert fields["Flagged Real Player"] == "1"


@pytest.mark.asyncio
async def test_unlinked_player_rejected():
    cog = _make_cog()
    ctx = _make_ctx()

    cog.deps.legacy_api.get_discord_links = AsyncMock(
        return_value=[_linked_account("OtherPlayer")]
    )

    await _invoke(cog, ctx, "Zezima")

    ctx.reply.assert_awaited_once_with("This account is not linked with your Discord.")
    cog.deps.public_api.get_feedback_export.assert_not_called()


@pytest.mark.asyncio
async def test_no_linked_accounts_rejected():
    cog = _make_cog()
    ctx = _make_ctx()

    cog.deps.legacy_api.get_discord_links = AsyncMock(return_value=[])

    await _invoke(cog, ctx, "Zezima")

    ctx.reply.assert_awaited_once_with("This account is not linked with your Discord.")


@pytest.mark.asyncio
async def test_unverified_account_rejected():
    cog = _make_cog()
    ctx = _make_ctx()

    cog.deps.legacy_api.get_discord_links = AsyncMock(
        return_value=[_linked_account("Zezima", verified=False)]
    )

    await _invoke(cog, ctx, "Zezima")

    ctx.reply.assert_awaited_once_with("This account is not linked with your Discord.")


@pytest.mark.asyncio
async def test_rate_limit_hit():
    cog = _make_cog()
    ctx = _make_ctx()
    ctx.author.id = 99999

    cog._rate_limits[99999] = 1715788800.0

    cog.deps.legacy_api.get_discord_links = AsyncMock(
        return_value=[_linked_account("Zezima")]
    )

    with patch(
        "bot_detector.discord_bot.cogs.feedback_list_commands.time"
    ) as mock_time:
        mock_time.time.return_value = 1715788800.0 + 100.0
        await _invoke(cog, ctx, "Zezima")

    ctx.reply.assert_awaited_once_with("You've already used this command today.")
    cog.deps.public_api.get_feedback_export.assert_not_called()


@pytest.mark.asyncio
async def test_rate_limit_expiry():
    cog = _make_cog()
    ctx = _make_ctx()
    ctx.author.id = 99998

    cog._rate_limits[99998] = 1715788800.0

    cog.deps.legacy_api.get_discord_links = AsyncMock(
        return_value=[_linked_account("Zezima")]
    )
    items = [_make_item("bot1", is_banned=True)]
    cog.deps.public_api.get_feedback_export = AsyncMock(
        return_value=_make_response(items)
    )

    with patch(
        "bot_detector.discord_bot.cogs.feedback_list_commands.time"
    ) as mock_time:
        mock_time.time.return_value = 1715788800.0 + 86500.0
        await _invoke(cog, ctx, "Zezima")

    ctx.reply.assert_awaited_once()
    call_kwargs = ctx.reply.call_args.kwargs
    assert "embed" in call_kwargs
    assert "files" in call_kwargs


@pytest.mark.asyncio
async def test_empty_feedback_returns_none():
    cog = _make_cog()
    ctx = _make_ctx()

    cog.deps.legacy_api.get_discord_links = AsyncMock(
        return_value=[_linked_account("Zezima")]
    )
    cog.deps.public_api.get_feedback_export = AsyncMock(return_value=None)

    with patch(
        "bot_detector.discord_bot.cogs.feedback_list_commands.time"
    ) as mock_time:
        mock_time.time.return_value = 1715788800.0
        await _invoke(cog, ctx, "Zezima")

    ctx.reply.assert_awaited_once_with("You have no feedback records.")


@pytest.mark.asyncio
async def test_name_normalization():
    cog = _make_cog()
    ctx = _make_ctx()

    cog.deps.legacy_api.get_discord_links = AsyncMock(
        return_value=[_linked_account("Zezi ma")]
    )
    cog.deps.public_api.get_feedback_export = AsyncMock(
        return_value=_make_response([_make_item("x")])
    )

    with patch(
        "bot_detector.discord_bot.cogs.feedback_list_commands.time"
    ) as mock_time:
        mock_time.time.return_value = 1715788800.0
        await _invoke(cog, ctx, "Zezi-ma_")

    cog.deps.public_api.get_feedback_export.assert_awaited_once_with("zezi ma")


@pytest.mark.asyncio
async def test_file_cleanup_even_if_reply_raises():
    cog = _make_cog()
    ctx = _make_ctx(reply_raises=RuntimeError("discord error"))

    cog.deps.legacy_api.get_discord_links = AsyncMock(
        return_value=[_linked_account("Zezima")]
    )
    cog.deps.public_api.get_feedback_export = AsyncMock(
        return_value=_make_response([_make_item("bot1", is_banned=True)])
    )

    created_dirs: list[str] = []
    original_mkdtemp = tempfile.mkdtemp

    def tracking_mkdtemp():
        d = original_mkdtemp()
        created_dirs.append(d)
        return d

    with (
        patch(
            "bot_detector.discord_bot.cogs.feedback_list_commands.tempfile.mkdtemp",
            side_effect=tracking_mkdtemp,
        ),
        patch("bot_detector.discord_bot.cogs.feedback_list_commands.time") as mock_time,
        pytest.raises(RuntimeError),
    ):
        mock_time.time.return_value = 1715788800.0
        await _invoke(cog, ctx, "Zezima")

    assert len(created_dirs) == 1
    assert not Path(created_dirs[0]).exists()


@pytest.mark.asyncio
async def test_csv_content_correctness():
    items = [
        _make_item("bot1", is_banned=True, vote=-1, prediction="Bot"),
        _make_item("legit1", is_banned=False, vote=0, prediction="Bot"),
        _make_item("real1", is_banned=False, vote=1, prediction="Real_Player"),
        _make_item("banned_real", is_banned=True, vote=1, prediction="Real_Player"),
    ]

    banned, not_banned, flagged_real = _split_feedback(items)

    csv_banned = _build_csv(banned)
    csv_not_banned = _build_csv(not_banned)
    csv_flagged = _build_csv(flagged_real)

    assert csv_banned == "player_name,banned\nbot1,yes\nbanned_real,yes"
    assert csv_not_banned == "player_name,banned\nlegit1,no\nreal1,no"
    assert csv_flagged == "player_name,banned\nreal1,no\nbanned_real,yes"


@pytest.mark.asyncio
async def test_csv_header_always_present():
    csv = _build_csv([])
    assert csv == "player_name,banned"


@pytest.mark.asyncio
async def test_safe_filenames_with_special_chars():
    assert _safe_slug("Zezima") == "zezima"
    assert _safe_slug("../../etc/passwd") == "etcpasswd"
    assert _safe_slug("a" * 20) == "a" * 12


@pytest.mark.asyncio
async def test_safe_filenames_empty_slug_fallback():
    slug = _safe_slug("!@#$%^&*()")
    assert len(slug) == 12
    assert slug.isalnum()


@pytest.mark.asyncio
async def test_embed_field_values_match_split():
    cog = _make_cog()
    ctx = _make_ctx()

    cog.deps.legacy_api.get_discord_links = AsyncMock(
        return_value=[_linked_account("Zezima")]
    )
    items = [
        _make_item("bot1", is_banned=True, vote=-1, prediction="Bot"),
        _make_item("bot2", is_banned=True, vote=-1, prediction="Bot"),
        _make_item("legit1", is_banned=False, vote=0, prediction="Bot"),
        _make_item("real1", is_banned=False, vote=1, prediction="Real_Player"),
    ]
    cog.deps.public_api.get_feedback_export = AsyncMock(
        return_value=_make_response(items)
    )

    with patch(
        "bot_detector.discord_bot.cogs.feedback_list_commands.time"
    ) as mock_time:
        mock_time.time.return_value = 1715788800.0
        await _invoke(cog, ctx, "Zezima")

    embed = ctx.reply.call_args.kwargs["embed"]
    fields = {f.name: f.value for f in embed.fields}
    assert fields["Total Feedback"] == "4"
    assert fields["Banned"] == "2"
    assert fields["Not Banned"] == "2"
    assert fields["Flagged Real Player"] == "1"


@pytest.mark.asyncio
async def test_rate_limit_updated_after_success():
    cog = _make_cog()
    ctx = _make_ctx()
    ctx.author.id = 55555

    cog.deps.legacy_api.get_discord_links = AsyncMock(
        return_value=[_linked_account("Zezima")]
    )
    cog.deps.public_api.get_feedback_export = AsyncMock(
        return_value=_make_response([_make_item("x")])
    )

    with patch(
        "bot_detector.discord_bot.cogs.feedback_list_commands.time"
    ) as mock_time:
        mock_time.time.return_value = 1715788800.0
        await _invoke(cog, ctx, "Zezima")

    assert cog._rate_limits[55555] == 1715788800.0
