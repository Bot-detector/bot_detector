import asyncio
import logging

import aiohttp
from bot_detector.database import Settings as DBSettings
from bot_detector.database import get_session_factory
from bot_detector.database.ban_broadcast import (
    BanBroadcastInterface,
    BanBroadcastRepo,
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
    embeds_failed_counter,
    embeds_sent_counter,
    start_metrics_server,
)
from pydantic import Field
from pydantic_settings import BaseSettings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)

# Legacy graveyard role ping; empty string disables the mention.
DEFAULT_ROLE_MENTION = "<@&893399220172767253>"


class Settings(BaseSettings):
    GRAVEYARD_WEBHOOK: str  # required; pydantic fails fast naming the missing var
    GRAVEYARD_ROLE_MENTION: str = DEFAULT_ROLE_MENTION
    CHUNK_SIZE: int = Field(default=50, ge=1)
    CHUNK_MAX_CHARS: int = Field(default=1000, ge=1, le=1024)
    CHUNK_SLEEP_SECONDS: float = Field(default=5.0, ge=0)
    METRICS_PORT: int = 8000


async def broadcast(
    session_factory: async_sessionmaker[AsyncSession],
    repo: BanBroadcastInterface,
    webhook: WebhookInterface,
    webhook_url: str,
    role_mention: str = DEFAULT_ROLE_MENTION,
    chunk_size: int = 50,
    chunk_max_chars: int = 1000,
    chunk_sleep_seconds: float = 5.0,
) -> int:
    """Apply predicted bot bans and broadcast the results to Discord.

    Reads pending ban counts and predicted bots, applies the bans
    (confirmed_ban = 1), then posts a totals embed, the banned names in
    chunks, and a completion embed with an optional role mention. All
    statements run in one transaction so the counts and names this run
    announces are the state the UPDATE acted on, and the write commits.

    Args:
        session_factory: SQLAlchemy async session factory.
        repo: Ban broadcast repository (counts, bots, apply).
        webhook: Discord webhook transport.
        webhook_url: Graveyard channel webhook URL.
        role_mention: Optional role mention posted with completion.
        chunk_size: Max names per names embed.
        chunk_max_chars: Max joined name chars per names embed.
        chunk_sleep_seconds: Pause between webhook posts.

    Returns:
        Number of bots banned (confirmed_ban set) in this run.
    """
    async with session_factory() as session, session.begin():
        counts = await repo.get_ban_counts(async_session=session)
        bots = await repo.select_banned_bots(async_session=session)
        bans_applied = await repo.apply_bot_bans(async_session=session)

    num_bots = len(bots)
    if bans_applied != num_bots:
        logger.warning(
            f"broadcast: applied {bans_applied} bans but selected {num_bots} bots "
            "(rows changed mid-run); embeds report the selected set"
        )
    logger.info(
        f"broadcast: totals={counts.total_bans:,} real_players="
        f"{counts.real_player_bans:,} no_data={counts.no_data_bans:,} bots={num_bots:,}"
    )

    err = await webhook.post(
        url=webhook_url,
        embeds=[build_totals_embed(counts=counts, bot_bans=num_bots)],
    )
    if err is not None:
        logger.error(f"broadcast: totals embed failed: {err}")
        embeds_failed_counter.inc()
    else:
        embeds_sent_counter.inc()

    if num_bots > 0:
        await _broadcast_names(
            bots=bots,
            webhook=webhook,
            webhook_url=webhook_url,
            chunk_size=chunk_size,
            chunk_max_chars=chunk_max_chars,
            chunk_sleep_seconds=chunk_sleep_seconds,
        )

        err = await webhook.post(
            url=webhook_url,
            embeds=[build_complete_embed(num_bans=num_bots)],
            content=role_mention or None,
        )
        if err is not None:
            logger.error(f"broadcast: complete embed failed: {err}")
            embeds_failed_counter.inc()
        else:
            embeds_sent_counter.inc()

    if bans_applied > 0:
        bans_applied_counter.inc(bans_applied)

    logger.info(f"broadcast: complete, {bans_applied} bans applied")
    return num_bots


async def _broadcast_names(
    bots: list[BannedBot],
    webhook: WebhookInterface,
    webhook_url: str,
    chunk_size: int,
    chunk_max_chars: int,
    chunk_sleep_seconds: float,
) -> None:
    chunks = chunk_bots(bots=bots, max_names=chunk_size, max_chars=chunk_max_chars)
    for i, chunk in enumerate(chunks, start=1):
        if i > 1:
            await asyncio.sleep(chunk_sleep_seconds)
        err = await webhook.post(
            url=webhook_url,
            embeds=[build_names_embed(chunk=chunk)],
        )
        if err is not None:
            logger.error(f"broadcast: names chunk {i}/{len(chunks)} failed: {err}")
            embeds_failed_counter.inc()
            continue
        embeds_sent_counter.inc()
        logger.debug(f"broadcast: names chunk {i}/{len(chunks)} sent")


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
            )
        finally:
            await async_engine.dispose()


async def run_async():
    await main()


def run():
    asyncio.run(run_async())


if __name__ == "__main__":
    run()
