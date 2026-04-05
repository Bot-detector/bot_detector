import logging

import discord

from bot_detector.discord_bot.config import Settings
from discord.ext.commands import Bot, Context
from bot_detector.discord_bot import cogs
from discord.ext import commands
from bot_detector.discord_bot.utils import checks
from discord.ext.commands import Greedy
from typing import Optional, Literal
from discord import Game, AllowedMentions, Intents

logger = logging.getLogger(__name__)

settings = Settings()

bot = Bot(
    command_prefix=settings.COMMAND_PREFIX,
    description="busting bots",
    case_insensitive=True,
    activity=Game("OSRS", type=discord.ActivityType.watching),
    allowed_mentions=AllowedMentions(
        everyone=False,
        roles=False,
        users=True,
    ),
    intents=Intents(
        messages=True,
        guilds=True,
        members=True,
        reactions=True,
        message_content=True,
    ),
)


@bot.check
async def globally_block_dms(ctx: Context):
    return ctx.guild is not None


@bot.check
async def globally_check_channel(ctx: Context):
    return await checks.is_allowed_channel(ctx)


@bot.event
async def setup_hook():
    await bot.add_cog(cogs.funCommands(bot))
    await bot.add_cog(cogs.botDetectiveCommands(bot))
    await bot.add_cog(cogs.errorHandler(bot))
    await bot.add_cog(cogs.rsnLinkingCommands(bot))
    await bot.add_cog(cogs.modCommands(bot))
    await bot.add_cog(cogs.projectStatsCommands(bot))
    await bot.add_cog(cogs.playerStatsCommands(bot))
    await bot.add_cog(cogs.mapCommands(bot))


# default events
@bot.event
async def on_ready():
    logger.info(f"We have logged in as {bot.user}")
    await bot.tree.sync()


@bot.event
async def on_connect():
    logger.info("Bot connected successfully.")
    logger.info(f"{Settings.COMMAND_PREFIX=}")


@bot.event
async def on_disconnect():
    logger.info("Bot disconnected.")


@bot.command()
@commands.guild_only()
@commands.is_owner()
async def sync(
    ctx: Context,
    guilds: Greedy[discord.Object],
    spec: Optional[Literal["~", "*", "^"]] = None,
) -> None:
    logger.debug(f"{ctx.author.name=}, {ctx.author.id=}, Requesting sync, {spec=}")
    if not guilds:
        if spec == "~":
            synced = await ctx.bot.tree.sync(guild=ctx.guild)
        elif spec == "*":
            ctx.bot.tree.copy_global_to(guild=ctx.guild)
            synced = await ctx.bot.tree.sync(guild=ctx.guild)
        elif spec == "^":
            ctx.bot.tree.clear_commands(guild=ctx.guild)
            await ctx.bot.tree.sync(guild=ctx.guild)
            synced = []
        else:
            synced = await ctx.bot.tree.sync()

        await ctx.send(
            f"Synced {len(synced)} commands {'globally' if spec is None else 'to the current guild.'}"
        )
        return

    ret = 0
    for guild in guilds:
        try:
            await ctx.bot.tree.sync(guild=guild)
        except discord.HTTPException:
            pass
        else:
            ret += 1

    await ctx.send(f"Synced the tree to {ret}/{len(guilds)}.")
