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
    while True:
        try:
            await bot.bot.start(token=settings.DISCORD_TOKEN)
        except discord.RateLimited as e:
            logger.warning(
                f"Discord rate limit exceeded. Restarting in {e.retry_after}s..."
            )
            await asyncio.sleep(e.retry_after)
            continue
        except discord.HTTPException as e:
            logger.error(
                {
                    "msg": "Discord HTTP Exception:",
                    "status": e.status,
                    "error": str(e),
                }
            )
            raise
        break


if __name__ == "__main__":
    run()
