import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("DISCORD_TOKEN", "test-token")
os.environ.setdefault("OSRS_ITEMS_USER_AGENT", "test-agent")

from bot_detector.discord_bot.cogs.feedback_list_commands import (
    _safe_slug,
    _split_feedback,
    create_file,
    feedbackListCommands,
    write_csv,
)
from bot_detector.public_api.v2.structs import (
    FeedbackExportItem,
    FeedbackExportResponse,
)


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
    ctx.command = MagicMock()
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


def _linked_account(name: str, verified: bool = True) -> dict:
    return {"name": name, "Verified_status": 1 if verified else 0}


@pytest.mark.asyncio
async def test_success_sends_file_and_embed():
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

    with (
        patch("bot_detector.discord_bot.cogs.feedback_list_commands.time") as mock_time,
        patch(
            "bot_detector.discord_bot.cogs.feedback_list_commands.is_supporter",
            return_value=False,
        ),
    ):
        mock_time.time.return_value = 1715788800.0
        mock_time.ctime.return_value = "Tue May 14 00:00:00 2026"
        await _invoke(cog, ctx, "Zezima")

    assert ctx.reply.await_count == 2

    file_call = ctx.reply.call_args_list[0]
    assert "file" in file_call.kwargs
    assert file_call.kwargs.get("ephemeral") is True
    assert "feedback.csv" in file_call.kwargs["file"].filename

    embed_call = ctx.reply.call_args_list[1]
    embed = embed_call.kwargs["embed"]
    assert embed.title == "Feedback Export"

    fields = {f.name: f.value for f in embed.fields}
    assert "Player" in fields
    assert fields["Player"] == "zezima"
    assert "Total Feedback: 3" in fields["Data"]
    assert "Banned: 1" in fields["Data"]
    assert "Not Banned: 2" in fields["Data"]
    assert "Flagged Real: 1" in fields["Data"]


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

    with (
        patch("bot_detector.discord_bot.cogs.feedback_list_commands.time") as mock_time,
        patch(
            "bot_detector.discord_bot.cogs.feedback_list_commands.is_supporter",
            return_value=False,
        ),
    ):
        mock_time.time.return_value = 1715788800.0 + 86500.0
        mock_time.ctime.return_value = "Tue May 14 00:00:00 2026"
        await _invoke(cog, ctx, "Zezima")

    assert ctx.reply.await_count == 2


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

    with (
        patch("bot_detector.discord_bot.cogs.feedback_list_commands.time") as mock_time,
        patch(
            "bot_detector.discord_bot.cogs.feedback_list_commands.is_supporter",
            return_value=False,
        ),
    ):
        mock_time.time.return_value = 1715788800.0
        mock_time.ctime.return_value = "Tue May 14 00:00:00 2026"
        await _invoke(cog, ctx, "Zezi-ma_")

    cog.deps.public_api.get_feedback_export.assert_awaited_once()
    call_kwargs = cog.deps.public_api.get_feedback_export.call_args.kwargs
    assert call_kwargs["player_name"] == "zezi ma"


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
        patch(
            "bot_detector.discord_bot.cogs.feedback_list_commands.is_supporter",
            return_value=False,
        ),
        pytest.raises(RuntimeError),
    ):
        mock_time.time.return_value = 1715788800.0
        await _invoke(cog, ctx, "Zezima")

    assert len(created_dirs) == 1
    assert not Path(created_dirs[0]).exists()


@pytest.mark.asyncio
async def test_split_feedback_correctness():
    items = [
        _make_item("bot1", is_banned=True, vote=-1, prediction="Bot"),
        _make_item("legit1", is_banned=False, vote=0, prediction="Bot"),
        _make_item("real1", is_banned=False, vote=1, prediction="Real_Player"),
        _make_item("banned_real", is_banned=True, vote=1, prediction="Real_Player"),
    ]

    banned, not_banned, flagged_real = _split_feedback(items)

    assert len(banned) == 2
    assert all(i.is_banned for i in banned)
    assert len(not_banned) == 2
    assert all(not i.is_banned for i in not_banned)
    assert len(flagged_real) == 2
    assert all(i.vote == 1 and i.prediction == "Real_Player" for i in flagged_real)


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
async def test_embed_data_field_values():
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

    with (
        patch("bot_detector.discord_bot.cogs.feedback_list_commands.time") as mock_time,
        patch(
            "bot_detector.discord_bot.cogs.feedback_list_commands.is_supporter",
            return_value=False,
        ),
    ):
        mock_time.time.return_value = 1715788800.0
        mock_time.ctime.return_value = "Tue May 14 00:00:00 2026"
        await _invoke(cog, ctx, "Zezima")

    embed_call = ctx.reply.call_args_list[1]
    embed = embed_call.kwargs["embed"]
    fields = {f.name: f.value for f in embed.fields}
    assert "Total Feedback: 4" in fields["Data"]
    assert "Banned: 2" in fields["Data"]
    assert "Not Banned: 2" in fields["Data"]
    assert "Flagged Real: 1" in fields["Data"]


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

    with (
        patch("bot_detector.discord_bot.cogs.feedback_list_commands.time") as mock_time,
        patch(
            "bot_detector.discord_bot.cogs.feedback_list_commands.is_supporter",
            return_value=False,
        ),
    ):
        mock_time.time.return_value = 1715788800.0
        mock_time.ctime.return_value = "Tue May 14 00:00:00 2026"
        await _invoke(cog, ctx, "Zezima")

    assert cog._rate_limits[55555] == 1715788800.0


@pytest.mark.asyncio
async def test_write_csv_creates_valid_csv(tmp_path):
    rows = [
        {"subject_name": "bot1", "is_banned": True},
        {"subject_name": "legit1", "is_banned": False},
    ]
    path = str(tmp_path / "test.csv")
    await write_csv(path, rows)

    import csv as csv_mod

    with open(path) as f:
        reader = csv_mod.DictReader(f)
        result = list(reader)

    assert len(result) == 2
    assert result[0]["subject_name"] == "bot1"
    assert result[1]["subject_name"] == "legit1"


@pytest.mark.asyncio
async def test_write_csv_empty_rows_no_file(tmp_path):
    path = str(tmp_path / "empty.csv")
    await write_csv(path, [])
    assert not Path(path).exists()


@pytest.mark.asyncio
async def test_create_file_returns_discord_file(tmp_path):
    rows = [{"a": "1", "b": "2"}]
    result = await create_file(rows, "test.csv", str(tmp_path))
    assert result.filename == "test.csv"


@pytest.mark.asyncio
async def test_supporter_gets_12_month_range():
    cog = _make_cog()
    ctx = _make_ctx()

    cog.deps.legacy_api.get_discord_links = AsyncMock(
        return_value=[_linked_account("Zezima")]
    )
    cog.deps.public_api.get_feedback_export = AsyncMock(
        return_value=_make_response([_make_item("x")])
    )

    with (
        patch("bot_detector.discord_bot.cogs.feedback_list_commands.time") as mock_time,
        patch(
            "bot_detector.discord_bot.cogs.feedback_list_commands.is_supporter",
            return_value=True,
        ),
    ):
        mock_time.time.return_value = 1715788800.0
        mock_time.ctime.return_value = "Tue May 14 00:00:00 2026"
        await _invoke(cog, ctx, "Zezima")

    call_kwargs = cog.deps.public_api.get_feedback_export.call_args.kwargs
    expected_ts = int(1715788800.0 - 12 * 30 * 24 * 60 * 60)
    assert call_kwargs["earliest_ts"] == expected_ts


@pytest.mark.asyncio
async def test_non_supporter_gets_3_month_range():
    cog = _make_cog()
    ctx = _make_ctx()

    cog.deps.legacy_api.get_discord_links = AsyncMock(
        return_value=[_linked_account("Zezima")]
    )
    cog.deps.public_api.get_feedback_export = AsyncMock(
        return_value=_make_response([_make_item("x")])
    )

    with (
        patch("bot_detector.discord_bot.cogs.feedback_list_commands.time") as mock_time,
        patch(
            "bot_detector.discord_bot.cogs.feedback_list_commands.is_supporter",
            return_value=False,
        ),
    ):
        mock_time.time.return_value = 1715788800.0
        mock_time.ctime.return_value = "Tue May 14 00:00:00 2026"
        await _invoke(cog, ctx, "Zezima")

    call_kwargs = cog.deps.public_api.get_feedback_export.call_args.kwargs
    expected_ts = int(1715788800.0 - 3 * 30 * 24 * 60 * 60)
    assert call_kwargs["earliest_ts"] == expected_ts
