from unittest.mock import AsyncMock, MagicMock

from bot_detector.database.ban_broadcast import BanCounts
from bot_detector.database.ban_broadcast import BannedBot
from bot_detector.database.ban_broadcast import BanBroadcastRepo
from bot_detector.discord_webhook import DiscordWebhookRepo
from bot_detector.job_broadcaster import core
from dst import run


def _resp_429(retry_after_s: float):
    resp = MagicMock()
    resp.status = 429
    resp.headers = {}
    resp.json = AsyncMock(return_value={"retry_after": retry_after_s})
    # usable as `async with session.post(...) as resp:`
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _session_factory():
    session = AsyncMock()
    # broadcast() opens its transaction via `async with session.begin():`
    txn = AsyncMock()
    txn.__aenter__ = AsyncMock(return_value=txn)
    txn.__aexit__ = AsyncMock(return_value=False)
    session.begin = MagicMock(return_value=txn)
    session_cm = AsyncMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=None)
    return MagicMock(return_value=session_cm)


def _repo(bots: list[BannedBot]):
    repo = MagicMock(spec=BanBroadcastRepo)
    repo.get_ban_counts = AsyncMock(
        return_value=BanCounts(total_bans=3, real_player_bans=0, no_data_bans=0)
    )
    repo.select_banned_bots = AsyncMock(return_value=bots)
    repo.apply_bot_bans = AsyncMock(
        side_effect=lambda async_session, player_ids: len(player_ids)
    )
    return repo


async def _storm_broadcast(retry_after_s: float):
    """broadcast() with the real webhook transport against a Discord that
    429s every post with the same retry_after; only severity varies."""
    session = MagicMock(post=MagicMock(return_value=_resp_429(retry_after_s)))
    webhook = DiscordWebhookRepo(session=session)
    bots = [
        BannedBot(player_id=i, name=f"bot{i}", prediction="vanilla") for i in range(3)
    ]
    banned = await core.broadcast(
        session_factory=_session_factory(),
        repo=_repo(bots),
        webhook=webhook,
        webhook_url="http://hook",
        chunk_size=2,
        chunk_sleep_seconds=5.0,
    )
    return banned, session


def test_broadcaster_rate_limit_storm_finishes_under_budget():
    """A 429 storm at retry_after=60 must still complete: bans applied, all
    4 posts exhausted at 3 attempts, and the retry sleeps must stay inside
    a sane cron window. Virtual clock: milliseconds of real time."""
    result = run(_storm_broadcast(retry_after_s=60.0))
    assert result.done, result.error
    banned, session = result.value
    assert banned == 3
    assert session.post.call_count == 12  # totals + 2 names + complete, x3 attempts
    # 4 posts x 2 sleeps x 60s + one 5s chunk pause = 485s of virtual time
    assert 480.0 <= result.virtual_time_s <= 600.0


def test_broadcaster_rate_limit_storm_hang_trips_deadline():
    """retry_after is unclamped in the transport, so one hostile 429 (86400s)
    parks the run far past any cron window; the virtual deadline catches this
    hang class in milliseconds. When the transport gains a retry_after cap the
    run completes and this test must flip to asserting completion."""
    result = run(_storm_broadcast(retry_after_s=86_400.0), until_s=1000.0)
    assert result.done is False
    assert result.error is None
    assert result.virtual_time_s == 1000.0
