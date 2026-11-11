import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from bot_detector.database.ban_broadcast import BanCounts, BannedBot
from bot_detector.database.ban_broadcast import BanBroadcastRepo
from bot_detector.database.ban_broadcast.interface import BanBroadcastInterface
from bot_detector.discord_webhook import Embed
from bot_detector.job_broadcaster import core
from bot_detector.job_broadcaster.embeds import chunk_bots
from bot_detector.wide_event import WideEventLogger
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
    repo.apply_bot_bans = AsyncMock(
        side_effect=lambda async_session, player_ids: len(player_ids)
    )
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
    bots = [
        BannedBot(player_id=i, name=f"bot{i}", prediction="vanilla") for i in range(5)
    ]
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
    bots = [
        BannedBot(player_id=i, name=f"bot{i}", prediction="vanilla") for i in range(6)
    ]
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
    bots = [BannedBot(player_id=0, name="bot0", prediction="vanilla")]
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
    bots = [BannedBot(player_id=0, name="bot0", prediction="vanilla")]
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

    repo = _make_repo(bots=[BannedBot(player_id=0, name="bot0", prediction="vanilla")])
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

    async def select_banned_bots(self, async_session, batch_size: int):
        await async_session.execute("SELECT id FROM Players")
        return [BannedBot(player_id=0, name="bot0", prediction="vanilla")]

    async def apply_bot_bans(self, async_session, player_ids: list[int]) -> int:
        result = await async_session.execute(
            "UPDATE Players SET confirmed_ban = 1 WHERE id IN :ids"
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
    bots = [
        BannedBot(player_id=i, name=f"bot{i}", prediction="vanilla") for i in range(7)
    ]
    chunks = chunk_bots(bots=bots, max_names=3)
    assert [len(c) for c in chunks] == [3, 3, 1]


def test_chunk_bots_respects_max_chars():
    bots = [
        BannedBot(player_id=0, name="a" * 20, prediction="vanilla") for _ in range(5)
    ]
    chunks = chunk_bots(bots=bots, max_names=50, max_chars=45)
    # two names (20 + 2 + 20 = 42 chars) fit, three (64 chars) do not
    assert [len(c) for c in chunks] == [2, 2, 1]


def test_chunk_bots_never_emits_empty_chunks():
    """Bug: a single over-limit name made chunk_bots append an empty chunk,
    producing an embed with an empty field (Discord rejects those)."""
    long_name = BannedBot(player_id=0, name="x" * 1200, prediction="vanilla")
    short = BannedBot(player_id=0, name="bot0", prediction="vanilla")
    chunks = chunk_bots(bots=[long_name, short], max_names=50, max_chars=1000)
    assert all(len(chunk) > 0 for chunk in chunks)
    assert chunks == [[long_name], [short]]


def test_chunk_bots_rejects_degenerate_limits():
    """max_names=0 / max_chars=0 (env-overridable) used to emit one empty
    chunk plus one chunk per bot - hammering the webhook with junk."""
    bots = [BannedBot(player_id=0, name="bot0", prediction="vanilla")]
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

    names = build_names_embed(chunk=[BannedBot(player_id=0, name="a", prediction="p")])
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


# --- DB retry mechanisms -------------------------------------------------


def _flaky_repo(fail_times: int, exc: Exception):
    """Repo whose get_ban_counts fails `fail_times` times before succeeding."""
    repo = _make_repo(bots=[BannedBot(player_id=0, name="bot0", prediction="vanilla")])
    inner = repo.get_ban_counts
    calls = {"n": 0}

    async def _maybe_fail(async_session):
        calls["n"] += 1
        if calls["n"] <= fail_times:
            raise exc
        return await inner(async_session)

    repo.get_ban_counts = AsyncMock(side_effect=_maybe_fail)
    repo.calls = calls
    return repo


@pytest.mark.asyncio
async def test_broadcast_retries_db_on_lock_wait_timeout(monkeypatch, caplog):
    """Lock waits / deadlocks surface as OperationalError; the transaction
    must be retried with backoff instead of killing the run."""
    from sqlalchemy.exc import OperationalError

    monkeypatch.setattr(core.asyncio, "sleep", AsyncMock(return_value=None))
    caplog.set_level(logging.INFO)
    repo = _flaky_repo(
        fail_times=1,
        exc=OperationalError(
            "UPDATE Players ...", {}, Exception("Lock wait timeout exceeded")
        ),
    )
    event = WideEventLogger(sample_ratio=0.0)

    banned = await core.broadcast(
        session_factory=_make_session_factory(),
        repo=repo,
        webhook=_make_webhook(),
        webhook_url="http://hook",
        db_backoff_seconds=0,
        event=event,
    )

    assert banned == 1
    assert repo.calls["n"] == 2
    ctx = _dict_records(caplog)[0]
    assert "db_retry_snapshot_attempt_1" in ctx


@pytest.mark.asyncio
async def test_broadcast_raises_after_exhausting_db_retries(monkeypatch):
    from sqlalchemy.exc import OperationalError

    monkeypatch.setattr(core.asyncio, "sleep", AsyncMock(return_value=None))
    repo = _flaky_repo(
        fail_times=99,
        exc=OperationalError("UPDATE Players ...", {}, Exception("deadlock")),
    )

    with pytest.raises(OperationalError):
        await core.broadcast(
            session_factory=_make_session_factory(),
            repo=repo,
            webhook=_make_webhook(),
            webhook_url="http://hook",
            db_attempts=3,
            db_backoff_seconds=0,
            event=WideEventLogger(sample_ratio=0.0),
        )

    assert repo.calls["n"] == 3


@pytest.mark.asyncio
async def test_broadcast_does_not_retry_non_transient_db_errors(monkeypatch):
    """Bad SQL / constraint violations are programming errors - retrying
    them would just re-run the same failure."""
    monkeypatch.setattr(core.asyncio, "sleep", AsyncMock(return_value=None))
    repo = _flaky_repo(fail_times=99, exc=ValueError("bad predicate"))

    with pytest.raises(ValueError):
        await core.broadcast(
            session_factory=_make_session_factory(),
            repo=repo,
            webhook=_make_webhook(),
            webhook_url="http://hook",
            db_attempts=3,
            db_backoff_seconds=0,
            event=WideEventLogger(sample_ratio=0.0),
        )

    assert repo.calls["n"] == 1


@pytest.mark.asyncio
async def test_broadcast_backoff_is_exponential(monkeypatch):
    from sqlalchemy.exc import OperationalError

    sleeps: list[float] = []

    async def _fake_sleep(seconds):
        sleeps.append(seconds)
        return None

    monkeypatch.setattr(core.asyncio, "sleep", _fake_sleep)
    repo = _flaky_repo(
        fail_times=2,
        exc=OperationalError("UPDATE Players ...", {}, Exception("deadlock")),
    )

    await core.broadcast(
        session_factory=_make_session_factory(),
        repo=repo,
        webhook=_make_webhook(),
        webhook_url="http://hook",
        db_attempts=3,
        db_backoff_seconds=5.0,
        event=WideEventLogger(sample_ratio=0.0),
    )

    assert sleeps == [5.0, 10.0]


@pytest.mark.asyncio
async def test_db_retries_counter_counts(monkeypatch):
    from prometheus_client import REGISTRY
    from sqlalchemy.exc import OperationalError

    monkeypatch.setattr(core.asyncio, "sleep", AsyncMock(return_value=None))
    sample = "job_broadcaster_db_retries_total"
    before = REGISTRY.get_sample_value(sample) or 0
    repo = _flaky_repo(
        fail_times=1,
        exc=OperationalError("UPDATE Players ...", {}, Exception("lock wait")),
    )

    await core.broadcast(
        session_factory=_make_session_factory(),
        repo=repo,
        webhook=_make_webhook(),
        webhook_url="http://hook",
        db_backoff_seconds=0,
        event=WideEventLogger(sample_ratio=0.0),
    )

    after = REGISTRY.get_sample_value(sample) or 0
    assert after - before == 1


@pytest.mark.asyncio
async def test_broadcast_sets_short_lock_wait_timeout():
    """Session-level innodb_lock_wait_timeout must be lowered so lock waits
    fail fast into the retry loop instead of hanging ~50s."""
    session = _FakeTxnSession()
    factory = MagicMock(return_value=session)

    await core.broadcast(
        session_factory=factory,
        repo=_FakeRepo(),
        webhook=_make_webhook(),
        webhook_url="http://hook",
        db_lock_wait_timeout=10,
        chunk_sleep_seconds=0,
        event=WideEventLogger(sample_ratio=0.0),
    )

    assert any("innodb_lock_wait_timeout" in stmt for stmt in session.statements)


# --- batched apply (lock-strategy) ---------------------------------------


def _batch_flaky_repo(fail_batches: int, exc: Exception, bots: list[BannedBot]):
    """Repo whose apply_bot_bans fails the first `fail_batches` batches."""
    repo = _make_repo(bots=bots)
    calls = {"n": 0}

    async def _maybe_fail(async_session, player_ids):
        calls["n"] += 1
        if calls["n"] <= fail_batches:
            raise exc
        return len(player_ids)

    repo.apply_bot_bans = AsyncMock(side_effect=_maybe_fail)
    repo.calls = calls
    return repo


@pytest.mark.asyncio
async def test_broadcast_applies_in_id_batches(monkeypatch):
    """Bots must be applied in chunks aligned with the names embeds - each
    chunk applied then announced, one transaction per chunk - so lock
    windows stay short and the embed pacing throttles the UPDATE rate."""
    bots = [
        BannedBot(player_id=i, name=f"bot{i}", prediction="vanilla") for i in range(5)
    ]
    repo = _batch_flaky_repo(fail_batches=0, exc=None, bots=bots)
    monkeypatch.setattr(core.asyncio, "sleep", AsyncMock(return_value=None))

    banned = await core.broadcast(
        session_factory=_make_session_factory(),
        repo=repo,
        webhook=_make_webhook(),
        webhook_url="http://hook",
        chunk_size=2,
        chunk_sleep_seconds=0,
        event=WideEventLogger(sample_ratio=0.0),
    )

    assert banned == 5
    assert repo.apply_bot_bans.await_count == 3
    sizes = [len(c.kwargs["player_ids"]) for c in repo.apply_bot_bans.await_args_list]
    assert sizes == [2, 2, 1]


@pytest.mark.asyncio
async def test_broadcast_retries_batch_on_lock_wait(monkeypatch):
    from sqlalchemy.exc import OperationalError

    monkeypatch.setattr(core.asyncio, "sleep", AsyncMock(return_value=None))
    bots = [BannedBot(player_id=0, name="bot0", prediction="vanilla")]
    repo = _batch_flaky_repo(
        fail_batches=1,
        exc=OperationalError("UPDATE Players ...", {}, Exception("Lock wait timeout")),
        bots=bots,
    )

    banned = await core.broadcast(
        session_factory=_make_session_factory(),
        repo=repo,
        webhook=_make_webhook(),
        webhook_url="http://hook",
        db_backoff_seconds=0,
        chunk_sleep_seconds=0,
        event=WideEventLogger(sample_ratio=0.0),
    )

    assert banned == 1
    assert repo.calls["n"] == 2


@pytest.mark.asyncio
async def test_broadcast_batch_failure_aborts_before_further_announce(monkeypatch):
    """If a batch exhausts retries, the run must raise before announcing
    anything beyond what was already applied+announced - a partial apply
    is never announced, and the next run (which re-selects
    confirmed_ban = 0) announces the remainder."""
    from sqlalchemy.exc import OperationalError

    monkeypatch.setattr(core.asyncio, "sleep", AsyncMock(return_value=None))
    bots = [
        BannedBot(player_id=i, name=f"bot{i}", prediction="vanilla") for i in range(4)
    ]
    repo = _batch_flaky_repo(
        fail_batches=99,
        exc=OperationalError("UPDATE Players ...", {}, Exception("deadlock")),
        bots=bots,
    )
    webhook = _make_webhook()

    with pytest.raises(OperationalError):
        await core.broadcast(
            session_factory=_make_session_factory(),
            repo=repo,
            webhook=webhook,
            webhook_url="http://hook",
            db_attempts=2,
            chunk_size=2,
            db_backoff_seconds=0,
            chunk_sleep_seconds=0,
            event=WideEventLogger(sample_ratio=0.0),
        )

    # only the totals embed went out; no names embeds, no completion
    titles = [p["embeds"][0].title for p in webhook.posts]
    assert titles == ["Pending Bans Stats"]


def _dict_records(caplog) -> list[dict]:
    return [r.msg for r in caplog.records if isinstance(r.msg, dict)]


@pytest.mark.asyncio
async def test_broadcast_emits_force_logged_wide_event(caplog):
    """Runs that applied bans must emit one structured wide event (log_reason
    = force), carrying db + webhook context, regardless of sampling."""
    from bot_detector.wide_event import WideEventLogger

    caplog.set_level(logging.INFO)
    bots = [BannedBot(player_id=0, name="bot0", prediction="vanilla")]
    event = WideEventLogger(sample_ratio=0.0)  # sampling off: force must win

    await core.broadcast(
        session_factory=_make_session_factory(),
        repo=_make_repo(bots=bots),
        webhook=_make_webhook(),
        webhook_url="http://hook",
        chunk_sleep_seconds=0,
        event=event,
    )

    events = _dict_records(caplog)
    assert len(events) == 1
    ctx = events[0]
    assert ctx["log_reason"] == "force"
    assert ctx["db"] == {
        "total_bans": 10,
        "real_player_bans": 3,
        "no_data_bans": 2,
        "bots_selected": 1,
        "bans_applied": 1,
    }
    assert ctx["webhook"] == {
        "totals_failed": False,
        "names_chunks": 1,
        "names_failed": 0,
        "complete_failed": False,
    }


@pytest.mark.asyncio
async def test_broadcast_quiet_run_respects_sampling(caplog):
    """No bans applied and no failures -> emission is up to the sampler."""
    from bot_detector.wide_event import WideEventLogger

    caplog.set_level(logging.INFO)
    event = WideEventLogger(sample_ratio=0.0)

    await core.broadcast(
        session_factory=_make_session_factory(),
        repo=_make_repo(bots=[]),
        webhook=_make_webhook(),
        webhook_url="http://hook",
        chunk_sleep_seconds=0,
        event=event,
    )

    assert _dict_records(caplog) == []


@pytest.mark.asyncio
async def test_broadcast_webhook_failure_force_logs(caplog):
    """A failed post must surface in the wide event even with zero bans,
    else a broken webhook is invisible whenever sampling skips the run."""
    from bot_detector.wide_event import WideEventLogger

    caplog.set_level(logging.INFO)
    event = WideEventLogger(sample_ratio=0.0)
    repo = _make_repo(bots=[])
    webhook = _make_webhook(fail_on={"Pending Bans Stats"})

    await core.broadcast(
        session_factory=_make_session_factory(),
        repo=repo,
        webhook=webhook,
        webhook_url="http://hook",
        chunk_sleep_seconds=0,
        event=event,
    )

    events = _dict_records(caplog)
    assert len(events) == 1
    assert events[0]["log_reason"] == "force"
    assert events[0]["webhook"]["totals_failed"] is True


@pytest.mark.asyncio
async def test_broadcast_error_lands_in_wide_event(caplog):
    """DB failures are recorded in the wide event at error level, then
    re-raised so the container exit code reflects the failed run."""
    from bot_detector.wide_event import WideEventLogger

    caplog.set_level(logging.INFO)
    event = WideEventLogger(sample_ratio=0.0)
    repo = _make_repo()
    repo.get_ban_counts = AsyncMock(side_effect=RuntimeError("db down"))

    with pytest.raises(RuntimeError, match="db down"):
        await core.broadcast(
            session_factory=_make_session_factory(),
            repo=repo,
            webhook=_make_webhook(),
            webhook_url="http://hook",
            chunk_sleep_seconds=0,
            event=event,
        )

    events = _dict_records(caplog)
    assert len(events) == 1
    assert events[0]["error"] == {"message": "db down"}


@pytest.mark.asyncio
async def test_broadcast_context_is_reset_after_run(caplog):
    """The token pattern must leave the logger's context empty after the
    run; stale state would leak into the next event in a long-lived process."""
    from bot_detector.wide_event import WideEventLogger

    caplog.set_level(logging.INFO)
    event = WideEventLogger(sample_ratio=1.0)

    await core.broadcast(
        session_factory=_make_session_factory(),
        repo=_make_repo(bots=[]),
        webhook=_make_webhook(),
        webhook_url="http://hook",
        chunk_sleep_seconds=0,
        event=event,
    )

    assert event.get() == {}
