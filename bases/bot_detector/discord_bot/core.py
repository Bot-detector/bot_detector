import asyncio
import logging

from bot_detector.discord_bot.config import Settings
from bot_detector.discord_bot.bot import Bot
from bot_detector.discord_bot.dependencies import BotDependencies

logger = logging.getLogger(__name__)


def run():
    asyncio.run(run_async())


async def run_async():
    settings = Settings()
    deps = BotDependencies(settings)
    bot = Bot(deps=deps)
    
    await bot.start(settings.DISCORD_TOKEN)


if __name__ == "__main__":
    run()
