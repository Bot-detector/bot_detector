import logging
from inspect import cleandoc

import discord
from discord.ext import commands
from discord.ext.commands import Cog, Context
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class Stats(BaseModel):
    total_bans: int
    total_real_players: int
    total_accounts: int


class projectStatsCommands(Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def get_active_installs(self) -> int | None:
        session = self.bot.session
        url = "https://api.runelite.net/runelite/pluginhub"

        response = await session.get(url)

        data = None
        if response.ok:
            data = await response.json()
            data = data.get("bot-detector")
        return data

    @commands.hybrid_command()
    async def stats(self, ctx: Context):
        logger.debug(f"{ctx.author.name=}, {ctx.author.id=}, Requesting stats")
        
        active_installs = await self.get_active_installs()
        active_installs = active_installs if active_installs else "N/A"
        logger.info(f"{active_installs=}")

        embed = discord.Embed(title="Bot Detector Plugin", color=0x00FF00)
        embed.add_field(
            name="= Project Stats =",
            inline=False,
            value=cleandoc(
                f"""
                Active Installs: {active_installs:,}
            """
            ),
        )

        embed.set_thumbnail(
            url="https://user-images.githubusercontent.com/5789682/117360948-60a24f80-ae87-11eb-8a5a-7ba57f85deb2.png"
        )
        await ctx.reply(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(projectStatsCommands(bot))
