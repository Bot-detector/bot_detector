import asyncio
import logging

from bot_detector.discord_bot import bot
from bot_detector.discord_bot.config import Settings

logger = logging.getLogger(__name__)


def run():
    asyncio.run(run_async())


async def run_async():
    settings = Settings()

    await bot.bot.start(token=settings.DISCORD_TOKEN)


if __name__ == "__main__":
    run()
