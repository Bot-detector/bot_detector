from unittest.mock import AsyncMock, MagicMock

import pytest
from bot_detector.database.ban_broadcast import BanCounts, BannedBot
from bot_detector.database.ban_broadcast import BanBroadcastRepo
from bot_detector.database.ban_broadcast.interface import BanBroadcastInterface
from bot_detector.discord_webhook import Embed
from bot_detector.job_broadcaster import core
from bot_detector.job_broadcaster.embeds import chunk_bots
from pydantic import ValidationError


def _make_session_factory():
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


def _make_repo(counts: BanCounts | None = None, bots: list[BannedBot] | None = None):
    repo = MagicMock(spec=BanBroadcastRepo)
    repo.get_ban_counts = AsyncMock(
        return_value=counts
        or BanCounts(total_bans=10, real_player_bans=3, no_data_bans=2)
    )
    repo.select_banned_bots = AsyncMock(return_value=bots or [])
    repo.apply_bot_bans = AsyncMock(return_value=len(bots or []))
    return repo


def _make_webhook(fail_on: set[str] | None = None):
    """Recording webhook fake; keys in fail_on make matching titles fail."""
    posts: list[dict] = []

    async def _post(url, embeds=None, content=None):
        title = embeds[0].title if embeds else ""
        if fail_on and title in fail_on:
            return Exception(f"post failed: {title}")
        posts.append({"url": url, "embeds": embeds or [], "content": content})
        return None

    webhook = MagicMock()
    webhook.post = AsyncMock(side_effect=_post)
    webhook.posts = posts
    return webhook


@pytest.mark.asyncio
async def test_broadcast_applies_bans_and_posts_all_embeds():
    bots = [BannedBot(name=f"bot{i}", prediction="vanilla") for i in range(5)]
    repo = _make_repo(bots=bots)
    webhook = _make_webhook()

    banned = await core.broadcast(
        session_factory=_make_session_factory(),
        repo=repo,
        webhook=webhook,
        webhook_url="http://hook",
        chunk_sleep_seconds=0,
    )

    assert banned == 5
    repo.apply_bot_bans.assert_awaited_once()
    titles = [p["embeds"][0].title for p in webhook.posts]
    assert titles[0] == "Pending Bans Stats"
    assert titles[-1] == "Bans Added!"
    # 5 bots, default chunk size 50 -> single names embed between the two
    assert titles.count("All Ye Bots Lose All Hope!") == 1


@pytest.mark.asyncio
async def test_broadcast_no_bots_skips_names_and_completion():
    """Legacy logged 'list index out of range' every quiet run (its SQL
    helper crashed building a namedtuple from an empty result set) and then
    broadcast nothing. The port must treat an empty bot list as a clean no-op
    after the totals embed."""
    repo = _make_repo(bots=[])
    webhook = _make_webhook()

    banned = await core.broadcast(
        session_factory=_make_session_factory(),
        repo=repo,
        webhook=webhook,
        webhook_url="http://hook",
        chunk_sleep_seconds=0,
    )

    assert banned == 0
    titles = [p["embeds"][0].title for p in webhook.posts]
    assert titles == ["Pending Bans Stats"]


@pytest.mark.asyncio
async def test_broadcast_chunks_names(monkeypatch):
    monkeypatch.setattr(core.asyncio, "sleep", AsyncMock(return_value=None))
    bots = [BannedBot(name=f"bot{i}", prediction="vanilla") for i in range(6)]
    repo = _make_repo(bots=bots)
    webhook = _make_webhook()

    await core.broadcast(
        session_factory=_make_session_factory(),
        repo=repo,
        webhook=webhook,
        webhook_url="http://hook",
        chunk_size=2,
        chunk_sleep_seconds=0,
    )

    names_posts = [
        p for p in webhook.posts if p["embeds"][0].title == "All Ye Bots Lose All Hope!"
    ]
    assert len(names_posts) == 3


@pytest.mark.asyncio
async def test_broadcast_webhook_failure_does_not_abort(monkeypatch):
    """Legacy popped names off the list, swallowed the webhook error with
    `except Exception: pass`, and still posted 'Bans Added!'. The port must
    keep going too - but surface the failure instead of hiding it."""
    monkeypatch.setattr(core.asyncio, "sleep", AsyncMock(return_value=None))
    bots = [BannedBot(name="bot0", prediction="vanilla")]
    repo = _make_repo(bots=bots)
    webhook = _make_webhook(fail_on={"All Ye Bots Lose All Hope!"})

    banned = await core.broadcast(
        session_factory=_make_session_factory(),
        repo=repo,
        webhook=webhook,
        webhook_url="http://hook",
        chunk_sleep_seconds=0,
    )

    # the failed names embed is skipped, completion still posts
    assert banned == 1
    titles = [p["embeds"][0].title for p in webhook.posts]
    assert "Bans Added!" in titles


@pytest.mark.asyncio
async def test_broadcast_role_mention_on_completion():
    bots = [BannedBot(name="bot0", prediction="vanilla")]
    repo = _make_repo(bots=bots)
    webhook = _make_webhook()

    await core.broadcast(
        session_factory=_make_session_factory(),
        repo=repo,
        webhook=webhook,
        webhook_url="http://hook",
        role_mention="<@&123>",
        chunk_sleep_seconds=0,
    )

    completion = webhook.posts[-1]
    assert completion["content"] == "<@&123>"


@pytest.mark.asyncio
async def test_broadcast_bans_counter_reflects_apply_result():
    """Legacy counted len(names) for its announcements; the metric must
    count what the UPDATE actually changed, ungated by embed logic."""
    from prometheus_client import REGISTRY

    repo = _make_repo(bots=[BannedBot(name="bot0", prediction="vanilla")])
    repo.apply_bot_bans = AsyncMock(return_value=7)

    sample = "job_broadcaster_bans_applied_total"
    before = REGISTRY.get_sample_value(sample) or 0

    await core.broadcast(
        session_factory=_make_session_factory(),
        repo=repo,
        webhook=_make_webhook(),
        webhook_url="http://hook",
        chunk_sleep_seconds=0,
    )

    after = REGISTRY.get_sample_value(sample) or 0
    assert after - before == 7


class _FakeTxn:
    """begin() context manager with commit-on-clean-exit semantics."""

    def __init__(self, session: "_FakeTxnSession") -> None:
        self._session = session

    async def __aenter__(self) -> "_FakeTxn":
        self._session.in_txn = True
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        self._session.in_txn = False
        if exc_type is None:
            self._session.committed = True
        return False


class _FakeTxnSession:
    """AsyncSession fake that refuses execute() outside a transaction.

    Mirrors real SQLAlchemy semantics: autobegin starts a transaction that
    session.close() rolls back, so writes without begin/commit are lost.
    """

    def __init__(self) -> None:
        self.in_txn = False
        self.committed = False
        self.statements: list[str] = []

    async def __aenter__(self) -> "_FakeTxnSession":
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    def begin(self) -> _FakeTxn:
        return _FakeTxn(self)

    async def scalar(self, statement, params=None) -> int:
        if not self.in_txn:
            raise AssertionError("scalar() outside transaction: rolled back")
        self.statements.append(str(statement))
        return 0

    async def execute(self, statement, params=None):
        if not self.in_txn:
            raise AssertionError(
                "execute() outside transaction: the UPDATE would be rolled "
                "back when the session closes"
            )
        self.statements.append(str(statement))
        result = MagicMock()
        result.mappings.return_value.all.return_value = [
            {"name": "bot0", "prediction": "vanilla"}
        ]
        result.rowcount = 1
        return result


class _FakeRepo(BanBroadcastInterface):
    """Repo wired to _FakeTxnSession like the real BanBroadcastRepo, so the
    commit test exercises the session the way production does."""

    async def get_ban_counts(self, async_session) -> BanCounts:
        total = await async_session.scalar("SELECT COUNT(*) bans")
        await async_session.scalar("SELECT COUNT(*) real_bans")
        await async_session.scalar("SELECT COUNT(*) no_data_bans")
        return BanCounts(total_bans=total, real_player_bans=0, no_data_bans=0)

    async def select_banned_bots(self, async_session) -> list[BannedBot]:
        await async_session.execute("SELECT name FROM Players")
        return [BannedBot(name="bot0", prediction="vanilla")]

    async def apply_bot_bans(self, async_session) -> int:
        result = await async_session.execute(
            "UPDATE Players pl JOIN prediction_latest pr ON pr.player_id = pl.id "
            "SET pl.confirmed_ban = 1"
        )
        return result.rowcount


@pytest.mark.asyncio
async def test_broadcast_commits_ban_update_in_transaction():
    """Bug: the UPDATE ran inside a session that never commits, so it rolled
    back on session close - bans were announced but never persisted."""
    session = _FakeTxnSession()
    factory = MagicMock(return_value=session)

    banned = await core.broadcast(
        session_factory=factory,
        repo=_FakeRepo(),
        webhook=_make_webhook(),
        webhook_url="http://hook",
        chunk_sleep_seconds=0,
    )

    assert banned == 1
    assert session.committed, "UPDATE ran without an open transaction: rolled back"
    assert any("UPDATE" in s.upper() for s in session.statements)


def test_chunk_bots_respects_max_names():
    bots = [BannedBot(name=f"bot{i}", prediction="vanilla") for i in range(7)]
    chunks = chunk_bots(bots=bots, max_names=3)
    assert [len(c) for c in chunks] == [3, 3, 1]


def test_chunk_bots_respects_max_chars():
    bots = [BannedBot(name="a" * 20, prediction="vanilla") for _ in range(5)]
    chunks = chunk_bots(bots=bots, max_names=50, max_chars=45)
    # two names (20 + 2 + 20 = 42 chars) fit, three (64 chars) do not
    assert [len(c) for c in chunks] == [2, 2, 1]


def test_chunk_bots_never_emits_empty_chunks():
    """Bug: a single over-limit name made chunk_bots append an empty chunk,
    producing an embed with an empty field (Discord rejects those)."""
    long_name = BannedBot(name="x" * 1200, prediction="vanilla")
    short = BannedBot(name="bot0", prediction="vanilla")
    chunks = chunk_bots(bots=[long_name, short], max_names=50, max_chars=1000)
    assert all(len(chunk) > 0 for chunk in chunks)
    assert chunks == [[long_name], [short]]


def test_chunk_bots_rejects_degenerate_limits():
    """max_names=0 / max_chars=0 (env-overridable) used to emit one empty
    chunk plus one chunk per bot - hammering the webhook with junk."""
    bots = [BannedBot(name="bot0", prediction="vanilla")]
    with pytest.raises(ValueError):
        chunk_bots(bots=bots, max_names=0)
    with pytest.raises(ValueError):
        chunk_bots(bots=bots, max_chars=0)


def test_chunk_bots_empty_list():
    assert chunk_bots(bots=[]) == []


def test_embed_payload_shape():
    embed = Embed(title="t", description="d", fields=[], thumbnail_url="http://g.gif")
    payload = embed.to_payload()
    assert payload["title"] == "t"
    assert payload["thumbnail"] == {"url": "http://g.gif"}
    assert "timestamp" not in payload


def test_embed_builders_match_legacy_text():
    """Lock the legacy embed copy in place (titles, descriptions incl. the
    trailing space, field names, thumbnails) so cleanup can't silently
    change what the graveyard channel sees."""
    from bot_detector.job_broadcaster.embeds import (
        build_complete_embed,
        build_names_embed,
        build_totals_embed,
    )

    counts = BanCounts(total_bans=10, real_player_bans=3, no_data_bans=2)
    totals = build_totals_embed(counts=counts, bot_bans=5)
    assert totals.title == "Pending Bans Stats"
    assert totals.description == "Latest Ban Totals From Our Hiscores Scrapes"
    assert [f.name for f in totals.fields] == [
        "Total Unapplied Bans",
        "Predicted as Real Player (Not Counted)",
        "No Hiscore Data (Not Counted)",
        "Predicted as Bots (These Count)",
    ]
    assert [f.value for f in totals.fields] == ["10", "3", "2", "5"]

    names = build_names_embed(chunk=[BannedBot(name="a", prediction="p")])
    assert names.title == "All Ye Bots Lose All Hope!"
    assert names.description == "1 Accounts"
    assert names.fields[0].name == "Bans Being Added"
    assert names.fields[0].inline is False

    complete = build_complete_embed(num_bans=5)
    assert complete.title == "Bans Added!"
    assert complete.description == (
        "Bans were added to the project's total. Time to check your kc! "
    )
    assert complete.fields[0].value == "5"


def test_settings_defaults():
    settings = core.Settings(
        _env_file=None,
        GRAVEYARD_WEBHOOK="http://hook",
    )
    assert settings.CHUNK_SIZE == 50
    assert settings.CHUNK_MAX_CHARS == 1000
    assert settings.CHUNK_SLEEP_SECONDS == 5.0
    assert settings.METRICS_PORT == 8000


def test_settings_requires_webhook():
    """Legacy crashed with a raw KeyError deep in its config module; the
    port must fail fast at startup naming the missing variable."""
    with pytest.raises(ValidationError):
        core.Settings(_env_file=None)


def test_settings_bounds_chunk_max_chars():
    """CHUNK_MAX_CHARS above Discord's 1024-char field limit would
    resurrect the legacy silent-400 bug via a config override."""
    with pytest.raises(ValidationError):
        core.Settings(
            _env_file=None, GRAVEYARD_WEBHOOK="http://hook", CHUNK_MAX_CHARS=5000
        )


def test_entrypoints_exist():
    assert callable(core.run)
    assert callable(core.run_async)
    assert callable(core.main)
