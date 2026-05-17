import csv
import hashlib
import io
import logging
import re
import shutil
import tempfile
import time
from pathlib import Path

import aiofiles
import discord
from bot_detector.discord_bot.dependencies import BotDependencies
from bot_detector.discord_bot.utils import (
    DEV_CHANNEL_TESTER_ROLE,
    PATREON_ROLE,
    VERIFIED_PLAYER_ROLE,
)
from bot_detector.discord_bot.utils.string_processing import to_jagex_name
from bot_detector.public_api.v2.structs import (
    FeedbackExportItem,
    FeedbackExportResponse,
)
from discord.ext import commands
from discord.ext.commands import Context

logger = logging.getLogger(__name__)

MONTH_SECONDS = 30 * 24 * 60 * 60


def _safe_slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]", "", name.lower())[:12]
    if not slug:
        slug = hashlib.sha256(name.encode()).hexdigest()[:12]
    return slug


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


async def write_csv(path: str, rows: list[dict]):
    if not rows:
        return

    output = io.StringIO()

    writer = csv.DictWriter(output, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)

    async with aiofiles.open(path, "w") as f:
        await f.write(output.getvalue())


async def create_file(
    content: list[dict],
    filename: str,
    tmp_dir: str,
) -> discord.File:
    path = Path(tmp_dir) / filename
    await write_csv(path=str(path), rows=content)
    return discord.File(path, filename=filename)


async def create_files(
    banned: list[dict],
    not_banned: list[dict],
    flagged_real: list[dict],
    slug: str,
    tmp_dir: str,
) -> list[discord.File]:
    epoch = int(time.time())
    files_to_send: list[discord.File] = []
    file_tuples = [
        ("banned", banned),
        ("not_banned", not_banned),
        ("flagged_real_player", flagged_real),
    ]
    for suffix, content in file_tuples:
        filename = f"{epoch}_{slug}_{suffix}.csv"
        path = await create_file(content=content, filename=filename, tmp_dir=tmp_dir)
        files_to_send.append(path)
    return files_to_send


class feedbackListCommands(commands.Cog):
    def __init__(self, bot: commands.Bot, deps: BotDependencies) -> None:
        self.bot = bot
        self.deps = deps
        self._rate_limits: dict[int, float] = {}

    async def get_discord_links(self, discord_id: str) -> list:
        assert self.deps.legacy_api is not None
        accounts = await self.deps.legacy_api.get_discord_links(discord_id=discord_id)
        accounts: list[dict]

        verified_names = [
            acc.get("name")
            for acc in (accounts or [])
            if acc.get("Verified_status") == 1
        ]
        return verified_names

    async def get_feedback_records(
        self, name: str, earliest_ts: int
    ) -> FeedbackExportResponse | None:
        assert self.deps.public_api is not None
        response = await self.deps.public_api.get_feedback_export(
            player_name=name,
            earliest_ts=earliest_ts,
        )

        if response is None:
            return None

        assert isinstance(response, FeedbackExportResponse)
        return response

    @commands.hybrid_command(
        "feedback_list",
        description="Export your feedback records as CSV files.",
    )
    @commands.has_any_role(VERIFIED_PLAYER_ROLE, DEV_CHANNEL_TESTER_ROLE)
    async def feedback_list(self, ctx: Context, *, player_name: str) -> None:
        _log = {"user_id": ctx.author.id, "player_name": player_name}
        logger.info(_log)
        if ctx.command is None:
            await ctx.reply("Please use the slash command `/feedback_list`.")
            return

        await ctx.defer()

        normalized = to_jagex_name(player_name)

        verified_names = await self.get_discord_links(discord_id=str(ctx.author.id))

        if normalized not in [to_jagex_name(n) for n in verified_names if n]:
            await ctx.reply("This account is not linked with your Discord.")
            return

        now = time.time()
        last_used = self._rate_limits.get(ctx.author.id, 0)
        if now - last_used < 86400.0:
            await ctx.reply("You've already used this command today.")
            return

        assert isinstance(ctx.author, discord.Member)
        is_patreon = PATREON_ROLE in ctx.author.roles
        if is_patreon:
            earliest_ts = int(now - 12 * MONTH_SECONDS)
        else:
            earliest_ts = int(now - 3 * MONTH_SECONDS)

        logger.info(_log | {"earliest_ts": earliest_ts})
        feedback = await self.get_feedback_records(
            name=normalized, earliest_ts=earliest_ts
        )

        if not feedback:
            logger.info(_log | {"detail": "no feedback records"})
            await ctx.reply("You have no feedback records.")
            return

        _log = _log | {"feedback_count": len(feedback.feedback)}
        logger.info(_log)

        banned, not_banned, real = _split_feedback(feedback=feedback.feedback)
        _log = _log | {
            "banned": len(banned),
            "not_banned": len(not_banned),
            "real": len(real),
        }
        logger.info(_log)

        tmp_dir = tempfile.mkdtemp()

        try:
            epoch = int(time.time())
            slug = _safe_slug(normalized)
            file = await create_file(
                content=[i.model_dump() for i in feedback.feedback],
                filename=f"{epoch}_{slug}_feedback.csv",
                tmp_dir=tmp_dir,
            )

            embed = discord.Embed(title="Feedback Export", color=discord.Color.blue())
            embed.add_field(name="Player", value=normalized, inline=True)
            embed.add_field(
                name="Data",
                value=(
                    f"- Total Feedback: {len(feedback.feedback)}\n"
                    f"- Banned: {len(banned)}\n"
                    f"- Not Banned: {len(not_banned)}\n"
                    f"- Flagged Real: {len(real)}"
                ),
                inline=False,
            )
            # date YYYY-MM-DD HH:MM:SS
            t = time.ctime(earliest_ts)
            m = f" earliest:\n{t}"
            embed.set_footer(text="Patreon:" if is_patreon else "Non-Patreon:" + m)
            await ctx.reply(files=[file], ephemeral=True)
            await ctx.reply(embed=embed)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        self._rate_limits[ctx.author.id] = now
