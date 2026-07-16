import logging

from bot_detector import logfmt
from bot_detector.discord_bot.core import run

__all__ = ["logfmt", "run"]

# discord.py loggers
logging.getLogger("discord.http").setLevel(logging.DEBUG)
logging.getLogger("discord").setLevel(logging.INFO)
logging.getLogger("discord.gateway").setLevel(logging.INFO)
logging.getLogger("discord.client").setLevel(logging.INFO)
