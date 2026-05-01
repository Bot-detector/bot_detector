import asyncio
import logging
import re
from typing import List

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

    async def _parse_pastebin(self, data: str) -> List[str]:
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

        embeds = []
        i = 0
        for batch in self._batch(players, n=21):
            embed = discord.Embed(title="Ban list", color=discord.Color.red())
            for player in batch:
                if not player:
                    continue
                banned = player.get("label_jagex") == 2
                value = f"```{banned}```" if banned else str(banned)
                embed.add_field(name=player.get("name"), value=value, inline=True)
            embed.set_footer(text="True=Banned, False=Not banned")
            embeds.append(embed)

            if i != 0 and i % 9 == 0:
                await ctx.reply(embeds=embeds)
                embeds = []
            i += 1

        if embeds:
            await ctx.reply(embeds=embeds)
