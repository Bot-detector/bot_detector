import asyncio
import logging
from collections.abc import Awaitable, Callable
from functools import partial
from typing import TypeVar

import aiohttp
import sqlalchemy as sqla
from bot_detector.database import Settings as DBSettings
from bot_detector.database import get_session_factory
from bot_detector.database.ban_broadcast import (
    BanBroadcastInterface,
    BanBroadcastRepo,
    BanCounts,
    BannedBot,
)
from bot_detector.discord_webhook import DiscordWebhookRepo, WebhookInterface
from bot_detector.job_broadcaster.embeds import (
    build_complete_embed,
    build_names_embed,
    build_totals_embed,
    chunk_bots,
)
from bot_detector.job_broadcaster.metrics import (
    bans_applied_counter,
    db_retries_counter,
    embeds_failed_counter,
    embeds_sent_counter,
    start_metrics_server,
)
from bot_detector.wide_event import EventLoggerInterface, WideEventLogger
from pydantic import Field
from pydantic_settings import BaseSettings
from sqlalchemy.exc import InterfaceError as SAInterfaceError
from sqlalchemy.exc import OperationalError as SAOperationalError
from sqlalchemy.exc import TimeoutError as SATimeoutError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)

T = TypeVar("T")

wide_event = WideEventLogger()

# Transient DB failures worth retrying: lock wait timeouts (1205), deadlocks
# (1213) and lost connections surface as OperationalError, pool checkout
# timeouts as TimeoutError, driver disconnects as InterfaceError. Anything
# else (bad SQL, constraint violations, programming errors) must fail loud.
RETRIABLE_DB_ERRORS = (SAOperationalError, SATimeoutError, SAInterfaceError)

# Legacy graveyard role ping; empty string disables the mention.
DEFAULT_ROLE_MENTION = "<@&893399220172767253>"


class Settings(BaseSettings):
    GRAVEYARD_WEBHOOK: str  # required; pydantic fails fast naming the missing var
    GRAVEYARD_ROLE_MENTION: str = DEFAULT_ROLE_MENTION
    CHUNK_SIZE: int = Field(default=50, ge=1)
    CHUNK_MAX_CHARS: int = Field(default=1000, ge=1, le=1024)
    CHUNK_SLEEP_SECONDS: float = Field(default=5.0, ge=0)
    DB_RETRY_ATTEMPTS: int = Field(default=3, ge=1, le=10)
    DB_RETRY_BACKOFF_SECONDS: float = Field(default=5.0, ge=0)
    DB_LOCK_WAIT_TIMEOUT: int = Field(default=10, ge=1, le=60)
    METRICS_PORT: int = 8000


# Players per SELECT page when streaming the pending-bot snapshot; purely a
# memory/round-trip knob, apply batching is driven by CHUNK_SIZE instead.
READ_PAGE_SIZE = 1000


async def broadcast(
    session_factory: async_sessionmaker[AsyncSession],
    repo: BanBroadcastInterface,
    webhook: WebhookInterface,
    webhook_url: str,
    role_mention: str = DEFAULT_ROLE_MENTION,
    chunk_size: int = 50,
    chunk_max_chars: int = 1000,
    chunk_sleep_seconds: float = 5.0,
    db_attempts: int = 3,
    db_backoff_seconds: float = 5.0,
    db_lock_wait_timeout: int = 10,
    event: EventLoggerInterface | None = None,
) -> int:
    """Apply predicted bot bans and broadcast the results to Discord.

    Lock-strategy: the pending bots are read in one snapshot transaction
    (counts + id-cursor pages), then applied in chunks - each chunk a
    single-table PK UPDATE in its own short transaction, immediately
    followed by that chunk's names embed. Lock windows stay in the
    milliseconds, concurrent writers interleave between chunks, and the
    embed-post pacing throttles the UPDATE rate for free. The applied set
    is the announced set by construction: only ids from the snapshot are
    updated, rows flagged mid-run wait for the next run.

    The snapshot and every chunk apply are retried on transient DB errors
    (lock wait timeouts, deadlocks, lost connections) with exponential
    backoff; the session's innodb_lock_wait_timeout is lowered first so
    waits fail fast into the retry loop instead of hanging.

    Accumulates one wide event for the whole run: counts, selected and
    applied bans, db retries, webhook outcomes. Emits it at the end -
    error level on failure, info with log_reason=force when bans were
    applied or a post failed, otherwise sampled.

    Args:
        session_factory: SQLAlchemy async session factory.
        repo: Ban broadcast repository (counts, bots, apply).
        webhook: Discord webhook transport.
        webhook_url: Graveyard channel webhook URL.
        role_mention: Optional role mention posted with completion.
        chunk_size: Max names per embed and players per apply transaction.
        chunk_max_chars: Max joined name chars per names embed.
        chunk_sleep_seconds: Pause between chunk iterations.
        db_attempts: Max tries for each DB transaction.
        db_backoff_seconds: Base for exponential retry backoff.
        db_lock_wait_timeout: Session innodb_lock_wait_timeout in seconds.
        event: Wide event logger; defaults to the module instance.

    Returns:
        Number of bots selected for banning (confirmed_ban set) this run.
    """
    if event is None:
        event = wide_event
    token = event.set({})
    try:
        counts, bots = await _with_db_retry(
            partial(
                _read_bans_snapshot,
                session_factory=session_factory,
                repo=repo,
                batch_size=READ_PAGE_SIZE,
                lock_wait_timeout=db_lock_wait_timeout,
            ),
            attempts=db_attempts,
            backoff_seconds=db_backoff_seconds,
            event=event,
            label="snapshot",
        )

        err = await webhook.post(
            url=webhook_url,
            embeds=[build_totals_embed(counts=counts, bot_bans=len(bots))],
        )
        webhook_ctx: dict = {"totals_failed": err is not None}
        if err is not None:
            logger.error(f"broadcast: totals embed failed: {err}")
            embeds_failed_counter.inc()

        num_bots = len(bots)
        bans_applied = 0
        chunks_failed = 0
        chunks_total = 0
        if num_bots > 0:
            bans_applied, chunks_total, chunks_failed = await _apply_and_announce(
                bots=bots,
                session_factory=session_factory,
                repo=repo,
                webhook=webhook,
                webhook_url=webhook_url,
                chunk_size=chunk_size,
                chunk_max_chars=chunk_max_chars,
                chunk_sleep_seconds=chunk_sleep_seconds,
                db_attempts=db_attempts,
                db_backoff_seconds=db_backoff_seconds,
                db_lock_wait_timeout=db_lock_wait_timeout,
                event=event,
            )
            webhook_ctx["names_chunks"] = chunks_total
            webhook_ctx["names_failed"] = chunks_failed

            err = await webhook.post(
                url=webhook_url,
                embeds=[build_complete_embed(num_bans=num_bots)],
                content=role_mention or None,
            )
            webhook_ctx["complete_failed"] = err is not None
            if err is not None:
                logger.error(f"broadcast: complete embed failed: {err}")
                embeds_failed_counter.inc()

        event.add(
            {
                "db": {
                    "total_bans": counts.total_bans,
                    "real_player_bans": counts.real_player_bans,
                    "no_data_bans": counts.no_data_bans,
                    "bots_selected": num_bots,
                    "bans_applied": bans_applied,
                },
                "settings": {
                    "chunk_size": chunk_size,
                    "chunk_max_chars": chunk_max_chars,
                    "role_mention": bool(role_mention),
                },
            }
        )
        if bans_applied != num_bots:
            logger.warning(
                f"broadcast: applied {bans_applied} bans but selected {num_bots} bots "
                "(rows changed mid-run); embeds report the selected set"
            )

        event.add({"webhook": webhook_ctx})
        if bans_applied > 0 or any(
            v for k, v in webhook_ctx.items() if k.endswith("failed")
        ):
            event.add({"force_log": True})
        if bans_applied > 0:
            bans_applied_counter.inc(bans_applied)
        return num_bots
    except Exception as exc:
        event.add({"error": {"message": str(exc)}})
        raise
    finally:
        final_ctx = event.get()
        force_log = bool(final_ctx.pop("force_log", False))
        if "error" in final_ctx:
            logger.error(final_ctx)
        elif force_log:
            final_ctx.update({"log_reason": "force"})
            logger.info(final_ctx)
        elif event.sample():
            final_ctx.update({"log_reason": "sample"})
            logger.info(final_ctx)
        event.reset(token)


async def _with_db_retry(
    operation: Callable[[], Awaitable[T]],
    attempts: int,
    backoff_seconds: float,
    event: EventLoggerInterface,
    label: str,
) -> T:
    """Run a DB operation, retrying transient errors with exponential backoff.

    Transactions are atomic (rollback on failure), so retries re-read a
    fresh snapshot and re-apply from scratch - no partial state exists
    between attempts within one operation. Exhausts into the last
    exception, which broadcast() records in the wide event and re-raises.
    """
    for attempt in range(1, attempts + 1):
        try:
            return await operation()
        except RETRIABLE_DB_ERRORS as exc:
            if attempt == attempts:
                raise
            delay = backoff_seconds * 2 ** (attempt - 1)
            logger.warning(
                f"broadcast: db {label} attempt {attempt}/{attempts} failed "
                f"({exc}); retrying in {delay:.0f}s"
            )
            db_retries_counter.inc()
            event.add(
                {
                    f"db_retry_{label}_attempt_{attempt}": {
                        "error": str(exc),
                        "backoff_s": delay,
                    }
                }
            )
            await asyncio.sleep(delay)
    raise AssertionError("unreachable: retry loop always returns or raises")


async def _read_bans_snapshot(
    session_factory: async_sessionmaker[AsyncSession],
    repo: BanBroadcastInterface,
    batch_size: int,
    lock_wait_timeout: int,
) -> tuple[BanCounts, list[BannedBot]]:
    """Counts + full pending-bot list in one transaction (one snapshot)."""
    async with session_factory() as session, session.begin():
        await _set_lock_wait_timeout(session=session, seconds=lock_wait_timeout)
        counts = await repo.get_ban_counts(async_session=session)
        bots = await repo.select_banned_bots(
            async_session=session, batch_size=batch_size
        )
    return counts, bots


async def _apply_batch(
    session_factory: async_sessionmaker[AsyncSession],
    repo: BanBroadcastInterface,
    player_ids: list[int],
    lock_wait_timeout: int,
) -> int:
    """Apply one batch of vetted ids in its own short transaction."""
    async with session_factory() as session, session.begin():
        await _set_lock_wait_timeout(session=session, seconds=lock_wait_timeout)
        return await repo.apply_bot_bans(async_session=session, player_ids=player_ids)


async def _set_lock_wait_timeout(session: AsyncSession, seconds: int) -> None:
    """Fail fast on lock waits (default 50s is most of a cron window).

    Session-scoped var, settable without extra grants; it persists on the
    pooled connection, which is fine - every use of this job's connections
    wants the short timeout.
    """
    await session.execute(
        sqla.text("SET SESSION innodb_lock_wait_timeout = :seconds"),
        params={"seconds": seconds},
    )


async def _apply_and_announce(
    bots: list[BannedBot],
    session_factory: async_sessionmaker[AsyncSession],
    repo: BanBroadcastInterface,
    webhook: WebhookInterface,
    webhook_url: str,
    chunk_size: int,
    chunk_max_chars: int,
    chunk_sleep_seconds: float,
    db_attempts: int,
    db_backoff_seconds: float,
    db_lock_wait_timeout: int,
    event: EventLoggerInterface,
) -> tuple[int, int, int]:
    """Apply each chunk of vetted bots, then announce it, in one loop.

    Apply-before-announce per chunk: a failed apply aborts the run before
    further announcements, and a failed embed never hides applied bans.
    The embed-pacing sleeps throttle the UPDATE rate as a side effect.

    Returns (bans_applied, chunks_total, chunks_failed); failures are
    logged inline and reflected in the wide event by the caller.
    """
    chunks = chunk_bots(bots=bots, max_names=chunk_size, max_chars=chunk_max_chars)
    bans_applied = 0
    chunks_failed = 0
    for i, chunk in enumerate(chunks, start=1):
        if i > 1:
            await asyncio.sleep(chunk_sleep_seconds)
        bans_applied += await _with_db_retry(
            partial(
                _apply_batch,
                session_factory=session_factory,
                repo=repo,
                player_ids=[bot.player_id for bot in chunk],
                lock_wait_timeout=db_lock_wait_timeout,
            ),
            attempts=db_attempts,
            backoff_seconds=db_backoff_seconds,
            event=event,
            label=f"batch_{i}",
        )
        err = await webhook.post(
            url=webhook_url,
            embeds=[build_names_embed(chunk=chunk)],
        )
        if err is not None:
            logger.error(f"broadcast: names chunk {i}/{len(chunks)} failed: {err}")
            embeds_failed_counter.inc()
            chunks_failed += 1
            continue
        embeds_sent_counter.inc()
        logger.debug(f"broadcast: names chunk {i}/{len(chunks)} sent")
    return bans_applied, len(chunks), chunks_failed


async def main():
    settings = Settings()
    start_metrics_server(port=settings.METRICS_PORT)
    session_factory, async_engine = get_session_factory(SETTINGS=DBSettings())
    async with aiohttp.ClientSession() as aiohttp_session:
        webhook = DiscordWebhookRepo(session=aiohttp_session)
        try:
            await broadcast(
                session_factory=session_factory,
                repo=BanBroadcastRepo(),
                webhook=webhook,
                webhook_url=settings.GRAVEYARD_WEBHOOK,
                role_mention=settings.GRAVEYARD_ROLE_MENTION,
                chunk_size=settings.CHUNK_SIZE,
                chunk_max_chars=settings.CHUNK_MAX_CHARS,
                chunk_sleep_seconds=settings.CHUNK_SLEEP_SECONDS,
                db_attempts=settings.DB_RETRY_ATTEMPTS,
                db_backoff_seconds=settings.DB_RETRY_BACKOFF_SECONDS,
                db_lock_wait_timeout=settings.DB_LOCK_WAIT_TIMEOUT,
                event=wide_event,
            )
        finally:
            await async_engine.dispose()


async def run_async():
    await main()


def run():
    asyncio.run(run_async())


if __name__ == "__main__":
    run()
