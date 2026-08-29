import logging
from typing import Literal, Optional

import discord
from bot_detector.discord_bot import cogs
from bot_detector.discord_bot.config import Settings
from bot_detector.discord_bot.dependencies import DEPS
from bot_detector.discord_bot.utils import checks
from discord import AllowedMentions, Game, Intents
from discord.ext import commands
from discord.ext.commands import Bot, Context, Greedy

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


@bot.hybrid_command()
@commands.guild_only()
@commands.is_owner()
async def sync(
    ctx: Context,
    guilds: Greedy[discord.Object],
    spec: Optional[Literal["~", "*", "^"]] = None,
) -> None:
    """Syncs the app command tree. Bot owner only.

    :param ctx: The context of the command.
    :param guilds: Optional list of guild ids to sync to.
    :param spec: Optional sync spec, `~` current guild, `*` copy global to current guild, `^` clear current guild.
    """
    logger.debug(
        {
            "author": ctx.author.name,
            "author_id": ctx.author.id,
            "guild": ctx.guild.name if ctx.guild else None,
            "guild_id": ctx.guild.id if ctx.guild else None,
            "msg": f"is using sync, {spec=}, guilds={[guild.id for guild in guilds]}",
        }
    )
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

        scope = "globally" if spec is None else "to the current guild"
        await ctx.send(f"Synced {len(synced)} commands {scope}.")
        logger.info(
            {
                "author": ctx.author.name,
                "author_id": ctx.author.id,
                "msg": f"synced {len(synced)} commands {scope}, {spec=}",
            }
        )
        return

    ret = 0
    for guild in guilds:
        try:
            await ctx.bot.tree.sync(guild=guild)
        except discord.HTTPException as error:
            logger.error(
                {
                    "author": ctx.author.name,
                    "author_id": ctx.author.id,
                    "msg": f"failed to sync the tree to guild {guild.id}",
                    "error": str(error),
                }
            )
        else:
            ret += 1

    await ctx.send(f"Synced the tree to {ret}/{len(guilds)}.")
    logger.info(
        {
            "author": ctx.author.name,
            "author_id": ctx.author.id,
            "msg": f"synced the tree to {ret}/{len(guilds)} guilds",
        }
    )
