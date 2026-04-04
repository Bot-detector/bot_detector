import logging
import random

import discord
from discord.ext import commands
from discord.ext.commands import Cog, Context

logger = logging.getLogger(__name__)


class funCommands(Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _web_request(self, url: str) -> dict | None:
        async with self.bot.session.get(url) as response:
            if response.status != 200:
                logger.error({"status": response.status, "url": url})
                return None
            return await response.json()

    @commands.hybrid_command(name="poke")
    async def poke(self, ctx: Context):
        logger.debug(f"{ctx.author.name=}, {ctx.author.id=}, requested a poke")
        url = "https://api.prd.osrsbotdetector.com"
        ping = await self._web_request(url)
        is_server_up = "Online" if ping is not None else "Uh-Oh"

        embed = discord.Embed(color=0x00FF)
        embed.add_field(name="Teehee", value=":3", inline=False)
        embed.add_field(
            name="Discord Ping:", value=f"{self.bot.latency:.3f} ms", inline=False
        )
        embed.add_field(name="BD API Status:", value=f"{is_server_up}", inline=False)
        await ctx.reply(embed=embed)

    @commands.hybrid_command()
    async def panic(self, ctx: Context):
        logger.debug(f"{ctx.author.name=}, {ctx.author.id=}, requested a panic")
        await ctx.send("https://i.imgur.com/xAhgsgC.png")

    @commands.hybrid_command(name="meow")
    async def meow(self, ctx: Context):
        logger.debug(f"{ctx.author.name=}, {ctx.author.id=}, requested a cat")
        if random.randint(0, 1) > 0:
            url = "https://cataas.com/cat/gif?json=true"
        else:
            url = "https://cataas.com/cat?json=true"

        data = await self._web_request(url)
        if data is None:
            await ctx.reply("Ouw souwce fo' cats am cuwwentwy down, sowwy :3")
        else:
            await ctx.reply("https://cataas.com" + data["url"])

    @commands.hybrid_command()
    async def woof(self, ctx: Context):
        logger.debug(f"{ctx.author.name=}, {ctx.author.id=}, requested a dog")
        url = "https://some-random-api.ml/img/dog"

        data = await self._web_request(url)
        if data is None:
            await ctx.reply("Who let the dogs out?")
        else:
            await ctx.reply(data.get("link"))

    @commands.hybrid_command(aliases=["bird"])
    async def birb(self, ctx: Context):
        logger.debug(f"{ctx.author.name=}, {ctx.author.id=}, requested a bird")
        url = "http://shibe.online/api/birds"

        data = await self._web_request(url)
        if data is None:
            await ctx.reply("Birds all flew away. :(")
        else:
            await ctx.reply(data[0])

    @commands.hybrid_command(aliases=["rabbit", "bun"])
    async def bunny(self, ctx: Context):
        logger.debug(f"{ctx.author.name=}, {ctx.author.id=}, requested a bunny")
        url = "https://api.bunnies.io/v2/loop/random/?media=gif,png"

        data = await self._web_request(url)
        if data is None:
            await ctx.reply("The buns went on the run.")
        else:
            await ctx.reply(data["media"]["gif"])


async def setup(bot: commands.Bot):
    await bot.add_cog(funCommands(bot))
