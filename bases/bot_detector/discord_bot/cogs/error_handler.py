import logging
import sys
import traceback

import aiohttp
from bot_detector.discord_bot.config import Settings
from bot_detector.discord_bot.dependencies import BotDependencies
from discord import Webhook
from discord.ext import commands
from discord.ext.commands import Context

logger = logging.getLogger(__name__)


class errorHandler(commands.Cog):
    def __init__(self, bot: commands.Bot, deps: BotDependencies) -> None:
        super().__init__()
        self.bot = bot
        self.deps = deps

    @commands.Cog.listener()
    async def on_command_error(self, ctx: Context, error):
        if hasattr(ctx.command, "on_error"):
            return

        cog = ctx.cog
        if cog:
            if cog._get_overridden_method(cog.cog_command_error) is not None:
                return

        ignored = (commands.CommandNotFound,)

        error = getattr(error, "original", error)

        if isinstance(error, ignored):
            logger.debug(f"ignored: {error}")
            return

        if isinstance(error, commands.DisabledCommand):
            await ctx.reply(f"{ctx.command} has been disabled.")
        elif isinstance(error, commands.MissingAnyRole):
            logger.debug(f"user: {ctx.author}, {error}")
            await ctx.reply("You are missing at least one of the required roles")
        elif isinstance(error, commands.MissingRequiredArgument):
            logger.debug(f"user: {ctx.author}, {error}")
            await ctx.reply(str(error))
        elif isinstance(error, commands.CheckFailure):
            await ctx.reply(
                "You can only message in the allowed channels, in the bot detector guild."
            )
        else:
            traceback.print_exception(
                type(error), error, error.__traceback__, file=sys.stderr
            )

            logger.error({"error": error})
            await ctx.send("An error occured.")

            webhook = Settings().WEBHOOK
            if webhook:
                async with aiohttp.ClientSession() as session:
                    webhook = Webhook.from_url(webhook, session=session)
                    error_traceback = traceback.format_exception(
                        type(error), error, error.__traceback__
                    )
                    error_message = (
                        f"`{ctx.author}` running `{ctx.command}` caused `{error.__class__.__name__}`\n"
                        f"Message Link: {ctx.message.jump_url}\n"
                        f"```{''.join(error_traceback)}```"
                    )
                    error_message = "".join(error_message)

                    for secret in getattr(self.deps.settings, "SECRETS", []):
                        error_message = error_message.replace(secret, "***")
                    await webhook.send(error_message, username="bd-error")
