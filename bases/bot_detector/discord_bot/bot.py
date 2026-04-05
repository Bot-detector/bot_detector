import logging

import discord
from bot_detector.discord_bot.config import Settings
from bot_detector.discord_bot.dependencies import BotDependencies
from discord.ext.commands import Bot, Context
from bot_detector.discord_bot import cogs
from discord.ext import commands
from bot_detector.discord_bot.utils import checks
from typing import Optional, Literal

logger = logging.getLogger(__name__)


class Bot(Bot):
    def __init__(
        self,
        deps: BotDependencies,
        *,
    ):
        super().__init__(*args, **kwargs)
        self.deps = deps
    
    @bot.check
    async def globally_block_dms(self, ctx: Context):
        return ctx.guild is not None
    
    @bot.check
    async def globally_check_channel(self, ctx: Context):
        return await checks.is_allowed_channel(ctx)


async def setup_hook(bot: Bot, deps: BotDependencies):
    await bot.add_cog(cogs.funCommands(bot, deps=deps))
    await bot.add_cog(cogs.botDetectiveCommands(bot, deps=deps))
    await bot.add_cog(cogs.errorHandler(bot, deps=deps))
    await bot.add_cog(cogs.rsnLinkingCommands(bot, deps=deps))
    await bot.add_cog(cogs.modCommands(bot, deps=deps))
    await bot.add_cog(cogs.projectStatsCommands(bot, deps=deps))
    await bot.add_cog(cogs.playerStatsCommands(bot, deps=deps))
    await bot.add_cog(cogs.mapCommands(bot, deps=deps))


async def run_async():
    settings = Settings()
    deps = BotDependencies(settings)
    bot = Bot(deps=deps)
    
    @bot.event
    async def on_ready():
        logger.info(f"We have logged in as {bot.user}")
        await bot.tree.sync()
    
    @bot.event
    async def on_connect():
        logger.info("Bot connected successfully.")
    
    @bot.event
    async def on_disconnect():
        logger.info("Bot disconnected.")


if __name__ == "__main__":
    run()
