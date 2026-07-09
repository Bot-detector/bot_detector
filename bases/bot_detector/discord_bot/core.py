import asyncio
import logging

import discord
from aiohttp import ClientResponse
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
        except discord.HTTPException as e:
            logger.error(
                {
                    "msg": "Discord HTTP Exception:",
                    "headers": dict(e.response.headers),
                    "error": str(e),
                }
            )
            if not isinstance(e.response, ClientResponse):
                break
            if e.response.status == 429:
                headers = dict(e.response.headers)
                sleep_time = headers.get("Retry-After", 60)
                sleep_time = (
                    sleep_time
                    if isinstance(sleep_time, (int, float))
                    else float(sleep_time)
                )
                logger.error(
                    f"Discord API rate limit exceeded. Retrying in {sleep_time} seconds..."
                )
                await asyncio.sleep(sleep_time)
            raise e
        break


if __name__ == "__main__":
    run()
