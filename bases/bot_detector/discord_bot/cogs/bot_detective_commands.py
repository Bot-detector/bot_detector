import asyncio
import logging
import re
import shutil
import tempfile
import time
from pathlib import Path

import discord
from bot_detector.discord_bot.dependencies import BotDependencies
from bot_detector.discord_bot.utils import (
    DETECTIVE_ROLE,
    HEAD_DETECTIVE_ROLE,
    OWNER_ROLE,
)
from discord.ext import commands
from discord.ext.commands import Context

logger = logging.getLogger(__name__)


class botDetectiveCommands(commands.Cog):
    def __init__(self, bot: commands.Bot, deps: BotDependencies) -> None:
        self.bot = bot
        self.deps = deps

    async def _get_pastebin(self, url: str) -> str | None:
        url = url.replace("https://pastebin.com/", "https://pastebin.com/raw/")
        assert self.deps.session is not None
        async with self.deps.session.get(url) as resp:
            if not resp.ok:
                return None
            return await resp.text()

    async def _parse_pastebin(self, data: str) -> list[str]:
        user_names = [line for line in data.split("\r\n")]
        match = r"^[a-zA-Z0-9_\- ]{1,12}$"
        user_names = [name for name in user_names if re.match(match, name)]
        user_names = list(set(user_names))
        logger.debug(f"parsed names: {len(user_names)}")
        return user_names

    def _batch(self, iterable, n=1):
        length = len(iterable)
        for ndx in range(0, length, n):
            yield iterable[ndx : min(ndx + n, length)]

    @commands.hybrid_command()
    @commands.has_any_role(DETECTIVE_ROLE, HEAD_DETECTIVE_ROLE, OWNER_ROLE)
    async def submit(self, ctx: Context, url: str) -> None:
        debug = {
            "author": ctx.author.name,
            "author_id": ctx.author.id,
            "msg": "Send submission",
        }
        logger.debug(debug)

        await ctx.defer()

        if not url.startswith("https://pastebin.com/"):
            await ctx.reply("Please submit a pastebin url.")
            return

        data = await self._get_pastebin(url)

        if data is None:
            await ctx.reply("could not get pastebin")
            return

        user_names = await self._parse_pastebin(data)

        await ctx.reply(
            f"Received, {len(user_names)}. Thank you for submitting your list"
        )
        logger.debug(f"posting, {len(user_names)} to api")

        assert self.deps.legacy_api is not None

        asyncio.gather(
            *[self.deps.legacy_api.create_player(name) for name in user_names]
        )

        logger.debug(f"[DONE] posting, {len(user_names)} to api")

    @commands.hybrid_command()
    @commands.has_any_role(DETECTIVE_ROLE, HEAD_DETECTIVE_ROLE, OWNER_ROLE)
    async def ban_list(self, ctx: Context, url: str) -> None:
        debug = {
            "author": ctx.author.name,
            "author_id": ctx.author.id,
            "msg": "Send ban list",
        }
        logger.debug(debug)

        await ctx.defer()

        if not url.startswith("https://pastebin.com/"):
            await ctx.reply("Please submit a pastebin url.")
            return

        data = await self._get_pastebin(url)

        if data is None:
            await ctx.reply("could not get pastebin")
            return

        user_names = await self._parse_pastebin(data)

        players = []
        assert self.deps.legacy_api is not None
        for name in user_names:
            player: dict = await self.deps.legacy_api.get_player(
                player_name=name.replace("_", " ")
            )  # type: ignore[assignment]
            players.append(player)

        logger.debug(f"got players: {len(players)}")
        players = [p for p in players if p is not None]
        logger.debug(f"got players after filter: {len(players)}")

        if not players:
            await ctx.reply("No valid players found.")
            return

        banned_names: list[str] = []
        not_banned_names: list[str] = []

        for player in players:
            name = player.get("name", "unknown")
            if player.get("label_jagex") == 2:
                banned_names.append(name)
            else:
                not_banned_names.append(name)

        epoch = int(time.time())
        tmp_dir = tempfile.mkdtemp()

        banned_path = Path(tmp_dir) / f"{epoch}_banned.txt"
        not_banned_path = Path(tmp_dir) / f"{epoch}_not_banned.txt"

        banned_path.write_text("\n".join(banned_names))
        not_banned_path.write_text("\n".join(not_banned_names))

        embed = discord.Embed(title="Ban List", color=discord.Color.red())
        embed.add_field(name="Total", value=str(len(players)), inline=True)
        embed.add_field(name="Banned", value=str(len(banned_names)), inline=True)
        embed.add_field(
            name="Not Banned", value=str(len(not_banned_names)), inline=True
        )

        files = [
            discord.File(banned_path, filename=banned_path.name),
            discord.File(not_banned_path, filename=not_banned_path.name),
        ]

        try:
            await ctx.reply(embed=embed, files=files)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
