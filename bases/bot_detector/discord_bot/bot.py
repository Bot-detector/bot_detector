import logging
from typing import Literal, Optional

import discord
from bot_detector.discord_bot import cogs
from bot_detector.discord_bot.config import Settings
from bot_detector.discord_bot.dependencies import DEPS
from bot_detector.discord_bot.utils import checks
from discord import AllowedMentions, Game, Intents
from discord.ext import commands
from discord.ext.commands import Bot, Context

logger = logging.getLogger(__name__)

bot = Bot(
    command_prefix=Settings().COMMAND_PREFIX,
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
    is_allowed = await checks.is_allowed_channel(ctx)
    return is_allowed


@bot.event
async def setup_hook():
    DEPS.init(settings=Settings())
    await bot.add_cog(cogs.funCommands(bot, deps=DEPS))
    await bot.add_cog(cogs.botDetectiveCommands(bot, deps=DEPS))
    await bot.add_cog(cogs.errorHandler(bot, deps=DEPS))
    await bot.add_cog(cogs.rsnLinkingCommands(bot, deps=DEPS))
    await bot.add_cog(cogs.modCommands(bot, deps=DEPS))
    await bot.add_cog(cogs.projectStatsCommands(bot, deps=DEPS))
    await bot.add_cog(cogs.playerStatsCommands(bot, deps=DEPS))
    await bot.add_cog(cogs.mapCommands(bot, deps=DEPS))
    await bot.add_cog(cogs.feedbackListCommands(bot, deps=DEPS))


# default events
@bot.event
async def on_ready():
    logger.info(f"We have logged in as {bot.user}")
    # await bot.tree.sync()


@bot.event
async def on_connect():
    logger.info("Bot connected successfully.")
    logger.info(f"{Settings().COMMAND_PREFIX=}")


@bot.event
async def on_disconnect():
    logger.info("Bot disconnected.")


@bot.hybrid_command(name="sync")
@commands.guild_only()
@commands.is_owner()
async def sync(
    ctx: Context,
    spec: Optional[Literal["~", "*", "^"]] = None,
    guild_id: Optional[int] = None,
) -> None:
    logger.debug(
        f"{ctx.author.name=}, {ctx.author.id=}, Requesting sync, {spec=}, {guild_id=}"
    )

    if guild_id is not None:
        await ctx.bot.tree.sync(guild=discord.Object(id=guild_id))
        await ctx.send(f"Synced the tree to guild {guild_id}.")
        return

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
