import logging
import traceback

import aiohttp
import discord
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
        elif isinstance(error, discord.RateLimited):
            logger.warning(
                {
                    "msg": "Discord rate limit exceeded",
                    "retry_after": error.retry_after,
                }
            )
            await self._safe_respond(
                ctx,
                f"The bot is being rate limited by Discord."
                f" Please try again in {error.retry_after:.0f}s.",
            )
        elif isinstance(error, discord.HTTPException):
            logger.error(
                {
                    "error": str(error),
                    "status": error.response.status,
                    "discord_code": error.code,
                }
            )
            await self._safe_respond(ctx, "An error occured.")
            await self._send_error_webhook(ctx, error)
        else:
            logger.error({"error": error}, exc_info=error)
            await self._safe_respond(ctx, "An error occured.")
            await self._send_error_webhook(ctx, error)

    async def _send_error_webhook(self, ctx: Context, error: Exception) -> None:
        webhook_url = Settings().WEBHOOK
        if not webhook_url:
            return
        tb = "".join(
            traceback.format_exception(type(error), error, error.__traceback__)
        )
        error_message = (
            f"`{ctx.author}` running `{ctx.command}` caused"
            f" `{error.__class__.__name__}`\n"
            f"Message Link: {ctx.message.jump_url}\n"
            f"```\n{tb}\n```"
        )
        try:
            async with aiohttp.ClientSession() as session:
                webhook = Webhook.from_url(webhook_url, session=session)
                await webhook.send(error_message, username="bd-error")
        except Exception as e:
            logger.error({"msg": "Failed to send error webhook", "error": str(e)})

    async def _safe_respond(self, ctx: Context, message: str):
        try:
            if ctx.interaction and ctx.interaction.response.is_done():
                await ctx.interaction.followup.send(message, ephemeral=True)
            else:
                await ctx.send(message)
        except Exception:
            logger.warning("Failed to respond to expired interaction")
