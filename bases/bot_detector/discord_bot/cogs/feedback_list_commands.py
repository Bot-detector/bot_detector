import hashlib
import logging
import re
import shutil
import tempfile
import time
from pathlib import Path

import discord
from bot_detector.discord_bot.dependencies import BotDependencies
from bot_detector.discord_bot.utils import VERIFIED_PLAYER_ROLE
from bot_detector.discord_bot.utils.string_processing import to_jagex_name
from bot_detector.structs.feedback import FeedbackExportItem
from discord.ext import commands
from discord.ext.commands import Context

logger = logging.getLogger(__name__)


def _safe_slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]", "", name.lower())[:12]
    if not slug:
        slug = hashlib.sha256(name.encode()).hexdigest()[:12]
    return slug


def _build_csv(items: list[FeedbackExportItem]) -> str:
    lines = ["player_name,banned"]
    for item in items:
        banned_str = "yes" if item.is_banned else "no"
        lines.append(f"{item.subject_name},{banned_str}")
    return "\n".join(lines)


def _split_feedback(
    feedback: list[FeedbackExportItem],
) -> tuple[
    list[FeedbackExportItem], list[FeedbackExportItem], list[FeedbackExportItem]
]:
    banned = [i for i in feedback if i.is_banned]
    not_banned = [i for i in feedback if not i.is_banned]
    flagged_real = [
        i for i in feedback if i.vote == 1 and i.prediction == "Real_Player"
    ]
    return banned, not_banned, flagged_real


class feedbackListCommands(commands.Cog):
    def __init__(self, bot: commands.Bot, deps: BotDependencies) -> None:
        self.bot = bot
        self.deps = deps
        self._rate_limits: dict[int, float] = {}

    @commands.hybrid_command(
        "feedback_list",
        description="Export your feedback records as CSV files.",
    )
    @commands.has_any_role(VERIFIED_PLAYER_ROLE)
    async def feedback_list(self, ctx: Context, *, player_name: str) -> None:
        await ctx.defer()

        normalized = to_jagex_name(player_name)

        assert self.deps.legacy_api is not None
        linked_accounts: list[dict] = await self.deps.legacy_api.get_discord_links(
            discord_id=str(ctx.author.id)
        )

        verified_names = [
            acc.get("name")
            for acc in (linked_accounts or [])
            if acc.get("Verified_status") == 1
        ]

        if normalized not in [to_jagex_name(n) for n in verified_names if n]:
            await ctx.reply("This account is not linked with your Discord.")
            return

        now = time.time()
        last_used = self._rate_limits.get(ctx.author.id, 0)
        if now - last_used < 86400.0:
            await ctx.reply("You've already used this command today.")
            return

        assert self.deps.public_api is not None
        response = await self.deps.public_api.get_feedback_export(normalized)

        if response is None:
            await ctx.reply("You have no feedback records.")
            return
        banned_items, not_banned_items, flagged_real_items = _split_feedback(
            feedback=[r for r in response.feedback if isinstance(r, FeedbackExportItem)]
        )

        epoch = int(now)
        slug = _safe_slug(normalized)
        tmp_dir = tempfile.mkdtemp()

        try:
            files_to_send: list[discord.File] = []
            for suffix, items in [
                ("banned", banned_items),
                ("not_banned", not_banned_items),
                ("flagged_real_player", flagged_real_items),
            ]:
                filename = f"{epoch}_{slug}_{suffix}.csv"
                path = Path(tmp_dir) / filename
                path.write_text(_build_csv(items))
                files_to_send.append(discord.File(path, filename=filename))

            embed = discord.Embed(title="Feedback Export", color=discord.Color.blue())
            embed.add_field(name="Player", value=normalized, inline=True)
            embed.add_field(
                name="Total Feedback",
                value=str(response.total_feedback),
                inline=True,
            )
            embed.add_field(name="Banned", value=str(len(banned_items)), inline=True)
            embed.add_field(
                name="Not Banned", value=str(len(not_banned_items)), inline=True
            )
            embed.add_field(
                name="Flagged Real Player",
                value=str(len(flagged_real_items)),
                inline=True,
            )

            await ctx.reply(embed=embed, files=files_to_send)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        self._rate_limits[ctx.author.id] = now
