import asyncio
import logging

import aiohttp
import discord
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from bot_detector.discord_bot.config import Settings
from bot_detector.database.discord import DiscordVerificationRepo
from bot_detector.public_api import PublicApiClient
from bot_detector.osrs_items import OsrsItemsClient
from discord.ext.commands import Bot, Context

logger = logging.getLogger(__name__)


def run():
    asyncio.run(run_async())


async def run_async():
    settings = Settings()

    activity = discord.Game("OSRS", type=discord.ActivityType.watching)
    allowed_mentions = discord.AllowedMentions(everyone=False, roles=False, users=True)
    intents = discord.Intents(
        messages=True, guilds=True, members=True, reactions=True, message_content=True
    )

    bot = Bot(
        allowed_mentions=allowed_mentions,
        command_prefix=settings.COMMAND_PREFIX,
        description="busting bots",
        case_insensitive=True,
        activity=activity,
        intents=intents,
    )

    bot.settings = settings

    @bot.check
    async def globally_block_dms(ctx: Context):
        return ctx.guild is not None

    @bot.event
    async def on_ready():
        logger.info(f"We have logged in as {bot.user}")

        session = aiohttp.ClientSession()
        bot.session = session
        bot.public_api = PublicApiClient(session=session)
        bot.osrs_items = OsrsItemsClient(session=session, user_agent=settings.OSRS_ITEMS_USER_AGENT)

        if settings.SQL_URI:
            engine = create_async_engine(settings.SQL_URI, echo=False)
            async_session_factory = sessionmaker(
                engine, class_=AsyncSession, expire_on_commit=False
            )
            bot.async_session_factory = async_session_factory
            bot.discord_repo = DiscordVerificationRepo()
        else:
            bot.async_session_factory = None
            bot.discord_repo = None
            logger.warning("No SQL_URI configured, database features disabled")

        try:
            from bot_detector.discord_bot.cogs.error_handler import errorHandler
            from bot_detector.discord_bot.cogs.fun_commands import funCommands
            from bot_detector.discord_bot.cogs.mod_commands import modCommands
            from bot_detector.discord_bot.cogs.project_stats import projectStatsCommands
            from bot_detector.discord_bot.cogs.bot_detective_commands import (
                botDetectiveCommands,
            )
            from bot_detector.discord_bot.cogs.map_commands import mapCommands
            from bot_detector.discord_bot.cogs.player_stats_commands import (
                playerStatsCommands,
            )
            from bot_detector.discord_bot.cogs.rsn_linking_commands import (
                rsnLinkingCommands,
            )

            await bot.add_cog(errorHandler(bot))
            await bot.add_cog(funCommands(bot))
            await bot.add_cog(modCommands(bot))
            await bot.add_cog(projectStatsCommands(bot))
            await bot.add_cog(botDetectiveCommands(bot))
            await bot.add_cog(mapCommands(bot))
            await bot.add_cog(playerStatsCommands(bot))
            await bot.add_cog(rsnLinkingCommands(bot))

            logger.info("All cogs loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load cogs: {e}")
            raise

    @bot.event
    async def on_connect():
        logger.info("Bot connected successfully.")
        logger.info(f"{settings.COMMAND_PREFIX=}")

    @bot.event
    async def on_disconnect():
        logger.info("Bot disconnected.")

    await bot.start(settings.DISCORD_TOKEN)


if __name__ == "__main__":
    run()
