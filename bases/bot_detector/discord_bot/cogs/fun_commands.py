import logging
import random
import time

import discord
from bot_detector.discord_bot.dependencies import BotDependencies
from discord.ext import commands
from discord.ext.commands import Cog, Context

logger = logging.getLogger(__name__)


class funCommands(Cog):
    def __init__(self, bot: commands.Bot, deps: BotDependencies) -> None:
        self.bot = bot
        self.deps = deps

    async def _web_request(self, url: str) -> dict | None:
        assert self.deps.session is not None, "Session is not initialized"
        async with self.deps.session.get(url) as response:
            if response.status != 200:
                logger.error({"status": response.status, "url": url})
                return None
            return await response.json()

    @commands.hybrid_command(name="poke")
    async def poke(self, ctx: Context):
        logger.debug(f"{ctx.author.name=}, {ctx.author.id=}, requested a poke")
        await ctx.defer()
        url = "https://api.prd.osrsbotdetector.com"

        start_time = time.time()
        ping = await self._web_request(url)
        latency = time.time() - start_time

        is_server_up = "Online" if ping is not None else "Uh-Oh"

        discord_latency = f"{self.bot.latency:.3f} s"
        api_latency = f"{latency:.3f} s"

        embed = discord.Embed(color=0x00FF)
        embed.add_field(name="Teehee", value=":3", inline=False)
        embed.add_field(name="Discord Ping:", value=discord_latency, inline=False)
        embed.add_field(name="BD API Ping:", value=api_latency, inline=False)
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

    # @commands.hybrid_command()
    # async def woof(self, ctx: Context):
    #     logger.debug(f"{ctx.author.name=}, {ctx.author.id=}, requested a dog")
    #     url = "https://some-random-api.ml/img/dog"

    #     data = await self._web_request(url)
    #     if data is None:
    #         await ctx.reply("Who let the dogs out?")
    #     else:
    #         await ctx.reply(data.get("link"))

    # @commands.hybrid_command(aliases=["bird"])
    # async def birb(self, ctx: Context):
    #     logger.debug(f"{ctx.author.name=}, {ctx.author.id=}, requested a bird")
    #     url = "http://shibe.online/api/birds"

    #     data = await self._web_request(url)
    #     if data is None:
    #         await ctx.reply("Birds all flew away. :(")
    #     else:
    #         await ctx.reply(data[0])

    @commands.hybrid_command(aliases=["rabbit", "bun"])
    async def bunny(self, ctx: Context):
        logger.debug(f"{ctx.author.name=}, {ctx.author.id=}, requested a bunny")
        url = "https://api.bunnies.io/v2/loop/random/?media=gif,png"

        data = await self._web_request(url)
        if data is None:
            await ctx.reply("The buns went on the run.")
        else:
            await ctx.reply(data["media"]["gif"])
