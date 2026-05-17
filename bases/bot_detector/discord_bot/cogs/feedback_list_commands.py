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
from bot_detector.discord_bot.utils import VERIFIED_PLAYER_ROLE
from bot_detector.discord_bot.utils.string_processing import to_jagex_name
from bot_detector.public_api.v2.structs import (
    FeedbackExportItem,
    FeedbackExportResponse,
)
from discord.ext import commands
from discord.ext.commands import Context

logger = logging.getLogger(__name__)


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
    logger.info(
        {
            "action": "split_feedback",
            "total": len(feedback),
            "banned": len(banned),
            "not_banned": len(not_banned),
            "flagged_real": len(flagged_real),
        }
    )
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
        path = Path(tmp_dir) / filename
        await write_csv(path=str(path), rows=content)
        files_to_send.append(discord.File(path, filename=filename))
    return files_to_send


class feedbackListCommands(commands.Cog):
    def __init__(self, bot: commands.Bot, deps: BotDependencies) -> None:
        self.bot = bot
        self.deps = deps
        self._rate_limits: dict[int, float] = {}

    async def get_discord_links(self, discord_id: str) -> list:
        logger.info(
            {
                "action": "get_discord_links",
                "discord_id": discord_id,
            }
        )
        assert self.deps.legacy_api is not None
        accounts = await self.deps.legacy_api.get_discord_links(discord_id=discord_id)
        accounts: list[dict]

        verified_names = [
            acc.get("name")
            for acc in (accounts or [])
            if acc.get("Verified_status") == 1
        ]
        logger.info(
            {
                "action": "get_discord_links_result",
                "discord_id": discord_id,
                "verified_names": verified_names,
            }
        )
        return verified_names

    async def get_feedback_records(self, name: str) -> FeedbackExportResponse | None:
        logger.info(
            {
                "action": "get_feedback_records",
                "player_name": name,
            }
        )
        assert self.deps.public_api is not None
        response = await self.deps.public_api.get_feedback_export(name)
        if response is None:
            logger.warning(f"Failed to fetch feedback for {name}")
            return None
        logger.info(
            {
                "action": "get_feedback_records_result",
                "player_name": name,
                "record_count": len(response.feedback),
            }
        )
        assert isinstance(response, FeedbackExportResponse)
        return response

    @commands.hybrid_command(
        "feedback_list",
        description="Export your feedback records as CSV files.",
    )
    @commands.has_any_role(VERIFIED_PLAYER_ROLE)
    async def feedback_list(self, ctx: Context, *, player_name: str) -> None:
        logger.info(
            {
                "action": "feedback_list_command",
                "user_id": ctx.author.id,
                "player_name": player_name,
            }
        )
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

        feedback = await self.get_feedback_records(normalized)

        if not feedback:
            await ctx.reply("You have no feedback records.")
            return

        logger.info(
            {
                "action": "feedback_list_command_result",
                "user_id": ctx.author.id,
                "player_name": player_name,
                "feedback_count": len(feedback.feedback),
            }
        )
        banned, not_banned, real = _split_feedback(feedback=feedback.feedback)

        slug = _safe_slug(normalized)
        tmp_dir = tempfile.mkdtemp()

        try:
            files = await create_files(
                banned=[i.model_dump() for i in banned],
                not_banned=[i.model_dump() for i in not_banned],
                flagged_real=[i.model_dump() for i in real],
                slug=slug,
                tmp_dir=tmp_dir,
            )

            embed = discord.Embed(title="Feedback Export", color=discord.Color.blue())
            embed.add_field(name="Player", value=normalized, inline=True)
            embed.add_field(
                name="Total Feedback",
                value=str(len(feedback.feedback)),
                inline=True,
            )
            embed.add_field(name="Banned", value=str(len(banned)), inline=True)
            embed.add_field(name="Not Banned", value=str(len(not_banned)), inline=True)
            embed.add_field(name="Flagged Real", value=str(len(real)), inline=True)

            await ctx.reply(embed=embed, files=files)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        self._rate_limits[ctx.author.id] = now
