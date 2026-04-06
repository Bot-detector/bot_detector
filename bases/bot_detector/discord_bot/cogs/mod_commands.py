import logging

import discord
from bot_detector.discord_bot.utils import (
    DISCORD_STAFF,
    OWNER_ROLE,
    VERIFICATION_STAFF,
)
from discord.ext import commands
from discord.ext.commands import Cog, Context

logger = logging.getLogger(__name__)


class modCommands(Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def _batch(self, iterable, n=1):
        length = len(iterable)
        for ndx in range(0, length, n):
            yield iterable[ndx : min(ndx + n, length)]

    @commands.hybrid_command()
    @commands.has_any_role(DISCORD_STAFF, OWNER_ROLE)
    async def warn(self, ctx: Context):
        logger.debug(f"{ctx.author.name=}, {ctx.author.id=}, is using warn")

        embed = discord.Embed(title="WARNING", color=0xFF0000)
        name = "= WARNING MESSAGE ="
        value = "**Do not attempt to contact the Jmods or Admins in any channel regarding the status of your Runescape account: Doing so will result in an automatic permanent ban.**\n**This is your only warning.**\n"
        url = "https://user-images.githubusercontent.com/5789682/117366156-59327480-ae8e-11eb-8b08-6cf815d8a36e.png"
        embed.add_field(name=name, value=value, inline=False)
        embed.set_thumbnail(url=url)
        await ctx.send(embed=embed)

    @commands.hybrid_command()
    @commands.has_any_role(DISCORD_STAFF, VERIFICATION_STAFF, OWNER_ROLE)
    async def admin_linked(self, ctx: Context, discord_id: str):
        logger.debug(
            f"{ctx.author.name=}, {ctx.author.id=}, is using admin_linked for {discord_id}"
        )

        await ctx.reply("Admin linked command - needs database implementation")
