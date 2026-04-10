import asyncio
import logging
from datetime import date, datetime, time

from bot_detector.database import Settings as DBSettings
from bot_detector.database import get_session_factory
from bot_detector.database.player import PlayerRepo
from bot_detector.event_queue.adapters.kafka import (
    KafkaConfig,
    KafkaLagProbe,
    KafkaProducerConfig,
    KafkaSettings,
)
from bot_detector.event_queue.core import QueueProducer
from bot_detector.event_queue.factory import QueueFactory
from bot_detector.event_queue.lag_probe import LagProbeProtocol
from bot_detector.event_queue.structs import ToScrapeStruct
from bot_detector.structs import MetaData, PlayerStruct
from bot_detector.wide_event import WideEventLogger
from pydantic_settings import BaseSettings

from .states import (
    ScrapeEvent,
    ScraperCtx,
    ScrapeState,
    _force_log,
    determine_event,
    scraper_sm,
)

logger = logging.getLogger(__name__)
wide_event = WideEventLogger()


class Settings(BaseSettings):
    LIMIT: int = 10_000
    MAX_LAG: int = 100_000


async def produce_players(
    players: list[PlayerStruct], player_queue: QueueProducer[ToScrapeStruct]
):
    if not players:
        return
    wide_event.add({"queue_players": {"count": len(players)}})
    metadata = MetaData(version=1, source="scrape_task_producer")
    player_structs = [
        ToScrapeStruct(metadata=metadata, player_data=p)
        for p in players
        if len(p.name) <= 13
    ]
    if player_structs:
        err = await player_queue.put(player_structs)
        if isinstance(err, Exception):
            raise err


async def process_players(
    async_session,
    player_repo: PlayerRepo,
    player_queue: QueueProducer,
    lag_probe: LagProbeProtocol,
    lag_topic: str,
    lag_group_id: str,
    limit: int = 10,
):
    ctx = ScraperCtx(days=20, limit=limit)
    state = ScrapeState.NORMAL
    last_day = date.today()

    while True:
        token = wide_event.set({})
        try:
            lag = await lag_probe.lag(topic=lag_topic, group_id=lag_group_id)

            if last_day != date.today():
                last_day = date.today()
                state = scraper_sm.handle(ctx, state, ScrapeEvent.NEW_DAY)

            if state == ScrapeState.DONE:
                now = datetime.now()
                end_of_today = datetime.combine(now.date(), time.max)

                time_remaining = end_of_today - now
                # at least sleep for 1 second
                sleep_time = max(int(time_remaining.total_seconds()), 1)
                wide_event.add({"done_for_day": {"sleep_seconds": sleep_time}})
                _force_log()
                await asyncio.sleep(sleep_time)
                continue

            if lag >= Settings().MAX_LAG:
                wide_event.add({"lag_throttle": {"lag": lag}})
                _force_log()
                await asyncio.sleep(10)
                continue

            wide_event.add(
                {
                    "fetch_params": {
                        "step": state.name,
                        "days": ctx.days,
                        "first_date": str(ctx.first_date),
                        "last_date": str(ctx.last_date),
                    }
                }
            )

            async with async_session() as session:
                players = await player_repo.select_player(
                    async_session=session,
                    player_id=ctx.player_id,
                    possible_ban=ctx.possible_ban,
                    confirmed_ban=ctx.confirmed_ban,
                    or_none=state == ScrapeState.NORMAL,
                    first_date=ctx.first_date,
                    last_date=ctx.last_date,
                    limit=ctx.limit,
                )

            await produce_players(players, player_queue)

            if players:
                ctx.last_fetched_id = players[-1].id

            event = determine_event(ctx, state, len(players) if players else 0)
            state = scraper_sm.handle(ctx, state, event)

        except Exception as exc:
            wide_event.add({"error": {"message": str(exc)}})
            raise
        finally:
            final_ctx = wide_event.get()
            if "error" in final_ctx:
                logger.error(final_ctx)
            elif final_ctx.pop("force_log", False):
                final_ctx["log_reason"] = "force"
                logger.info(final_ctx)
            elif wide_event.sample():
                final_ctx["log_reason"] = "sample"
                logger.info(final_ctx)
            wide_event.reset(token)


async def main():
    async_session, async_engine = get_session_factory(SETTINGS=DBSettings())
    cfg = KafkaConfig(
        topic="players.to_scrape",
        bootstrap_servers=KafkaSettings().bootstrap_servers,
        producer=True,
        consumer=False,
        producer_config=KafkaProducerConfig(
            partition_key_fn=lambda m: str(m.player_data.id % 10)
        ),
    )
    player_queue = QueueFactory.create_queue(ToScrapeStruct, "producer", "kafka", cfg)
    if isinstance(player_queue, Exception):
        raise player_queue

    lag_probe = KafkaLagProbe(KafkaSettings().bootstrap_servers)
    if isinstance(lag_probe, Exception):
        raise lag_probe

    await player_queue.start()
    await lag_probe.start()

    assert isinstance(player_queue, QueueProducer)
    try:
        await process_players(
            async_session,
            PlayerRepo(),
            player_queue,
            lag_probe,
            "players.to_scrape",
            "scraper",
            Settings().LIMIT,
        )
    finally:
        await async_engine.dispose()
        await lag_probe.stop()
        await player_queue.stop()


if __name__ == "__main__":
    asyncio.run(main())
