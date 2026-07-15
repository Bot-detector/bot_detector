import os
from unittest.mock import AsyncMock, patch

import discord
import pytest

os.environ.setdefault("DISCORD_TOKEN", "test-token")
os.environ.setdefault("OSRS_ITEMS_USER_AGENT", "test-agent")

from bot_detector.discord_bot import core


@pytest.mark.asyncio
async def test_ratelimited_sleeps_and_retries():
    """RateLimited should sleep retry_after seconds then retry the loop."""
    call_count = 0

    async def fake_start(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise discord.RateLimited(retry_after=0.01)

    with (
        patch.object(core.bot.bot, "start", side_effect=fake_start),
        patch.object(core.asyncio, "sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        await core.run_async()

    assert call_count == 2
    mock_sleep.assert_awaited_once_with(0.01)


@pytest.mark.asyncio
async def test_http_exception_reraises():
    """Non-rate-limit HTTPException should re-raise, not loop."""

    async def fake_start(**kwargs):
        raise discord.HTTPException(
            response=type(
                "FakeResponse",
                (),
                {"status": 500, "reason": "Internal Server Error", "headers": {}},
            )(),
            message="Internal error",
        )

    with (
        patch.object(core.bot.bot, "start", side_effect=fake_start),
        pytest.raises(discord.HTTPException),
    ):
        await core.run_async()


@pytest.mark.asyncio
async def test_clean_start_exits_loop():
    """If bot.start returns cleanly, run_async should exit without retrying."""

    async def fake_start(**kwargs):
        pass

    with patch.object(core.bot.bot, "start", side_effect=fake_start):
        await core.run_async()


@pytest.mark.asyncio
async def test_ratelimited_does_not_reraise():
    """RateLimited should be swallowed (retry), not propagated to caller."""
    call_count = 0

    async def fake_start(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise discord.RateLimited(retry_after=0.01)

    with (
        patch.object(core.bot.bot, "start", side_effect=fake_start),
        patch.object(core.asyncio, "sleep", new_callable=AsyncMock),
    ):
        await core.run_async()

    assert call_count == 2
