import asyncio
import logging
from bot_detector.discord_bot.config import Settings
from bot_detector.discord_bot import bot

logger = logging.getLogger(__name__)


def run():
    asyncio.run(run_async())


async def run_async():
    await bot.bot.start(Settings().DISCORD_TOKEN)


if __name__ == "__main__":
    run()
