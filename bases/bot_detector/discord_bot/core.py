import asyncio
import logging

import discord
from bot_detector.discord_bot import bot
from bot_detector.discord_bot.config import Settings

logger = logging.getLogger(__name__)


def run():
    asyncio.run(run_async())


async def run_async():
    settings = Settings()
    try:
        await bot.bot.start(token=settings.DISCORD_TOKEN)
    except discord.HTTPException as e:
        logger.error(f"Discord HTTP Exception: {e.response.headers} {e}")
        raise e


if __name__ == "__main__":
    run()
