"""Monkey patch for the firehose container under the smoke profile.

Runs via PYTHONPATH (sitecustomize is imported automatically at
interpreter startup, after site-packages are on the path). It points
the Discord OAuth base url at the smoke network's stub server, so the
keyed-auth chain (token -> identity -> db user -> permissions) runs
end-to-end without calling discord.com.
"""

import os

OVERRIDE = os.environ.get("DISCORD_API_BASE_OVERRIDE")
if OVERRIDE:
    from bot_detector.firehose.app.auth import discord

    discord.DISCORD_API_BASE = OVERRIDE
