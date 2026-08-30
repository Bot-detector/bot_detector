import logging
from typing import Literal

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
    settings = Settings()
    DEPS.init(settings=settings)
    await bot.add_cog(cogs.funCommands(bot, deps=DEPS))
    await bot.add_cog(cogs.botDetectiveCommands(bot, deps=DEPS))
    await bot.add_cog(cogs.errorHandler(bot, deps=DEPS))
    await bot.add_cog(cogs.rsnLinkingCommands(bot, deps=DEPS))
    await bot.add_cog(cogs.modCommands(bot, deps=DEPS))
    await bot.add_cog(cogs.projectStatsCommands(bot, deps=DEPS))
    await bot.add_cog(cogs.playerStatsCommands(bot, deps=DEPS))
    await bot.add_cog(cogs.mapCommands(bot, deps=DEPS))
    await bot.add_cog(cogs.feedbackListCommands(bot, deps=DEPS))
    await sync_command_tree(settings=settings)


async def sync_command_tree(settings: Settings) -> None:
    # guild scoped sync is instant, global sync takes up to an hour to propagate
    if settings.SYNC_GUILD_ID is None:
        logger.warning("SYNC_GUILD_ID is not set, skipping startup command tree sync")
        return
    guild = discord.Object(id=settings.SYNC_GUILD_ID)
    bot.tree.copy_global_to(guild=guild)
    synced = await bot.tree.sync(guild=guild)
    logger.info(
        {"msg": f"synced {len(synced)} commands to guild {guild.id} on startup"}
    )


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
async def sync(ctx: Context, scope: Literal["local", "global"]) -> None:
    """Syncs the app command tree and clears the other scope. Bot owner only.

    :param ctx: The context of the command.
    :param scope: `local` syncs to the current guild and deletes global commands, `global` syncs global commands and deletes the current guild's commands.
    """
    logger.debug(
        {
            "author": ctx.author.name,
            "author_id": ctx.author.id,
            "guild": ctx.guild.name if ctx.guild else None,
            "guild_id": ctx.guild.id if ctx.guild else None,
            "msg": f"is using sync, {scope=}",
        }
    )
    try:
        if scope == "local":
            ctx.bot.tree.copy_global_to(guild=ctx.guild)
            synced = await ctx.bot.tree.sync(guild=ctx.guild)
            ctx.bot.tree.clear_commands(guild=None)
            await ctx.bot.tree.sync()
            await ctx.send(
                f"Synced {len(synced)} commands to the current guild, "
                "deleted all global commands."
            )
        else:
            synced = await ctx.bot.tree.sync()
            ctx.bot.tree.clear_commands(guild=ctx.guild)
            await ctx.bot.tree.sync(guild=ctx.guild)
            await ctx.send(
                f"Synced {len(synced)} global commands, "
                "deleted the current guild's commands."
            )
    except discord.HTTPException as error:
        logger.error(
            {
                "author": ctx.author.name,
                "author_id": ctx.author.id,
                "msg": f"failed to sync, {scope=}",
                "error": str(error),
            }
        )
        await ctx.send(f"Failed to sync {scope} commands.")
        return
    logger.info(
        {
            "author": ctx.author.name,
            "author_id": ctx.author.id,
            "msg": f"synced {len(synced)} commands, {scope=}",
        }
    )
