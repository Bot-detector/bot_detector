import asyncio
import logging
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta

from bot_detector.database import Settings as DBSettings
from bot_detector.database import get_session_factory
from bot_detector.database.player import PlayerRepo
from bot_detector.event_queue.adapters.kafka import (
    KafkaConfig,
    KafkaConsumerConfig,
    KafkaProducerConfig,
)
from bot_detector.event_queue.core import Queue
from bot_detector.event_queue.factory import QueueFactory
from bot_detector.kafka import Settings as KafkaSettings
from bot_detector.kafka import ToScrapeStruct
from bot_detector.structs import MetaData, PlayerStruct
from bot_detector.wide_event import WideEventLogger
from pydantic_settings import BaseSettings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from typing_extensions import Literal

logger = logging.getLogger(__name__)
wide_event = WideEventLogger()


def _force_log() -> None:
    wide_event.add({"force_log": True})


class Settings(BaseSettings):
    LIMIT: int = 10_000


@dataclass
class FetchParams:
    step: Literal["normal", "possible_ban", "confirmed_ban"]
    days: int
    first_date: date | None = None
    last_date: date | None = None
    confirmed_ban: bool = False
    possible_ban: bool = False
    player_id: int = 0
    limit: int = 10_000
    done: bool = False

    def __post_init__(self):
        self._update_step_flags()
        self.update_date(days=self.days, infinity=False)

    def update_date(self, days: int, infinity: bool = False) -> None:
        self.days = days
        delta = timedelta(days=365) if infinity else timedelta(days=self.days)
        self.first_date = date.today() - delta
        self.last_date = date.today() - timedelta(days=self.days - 1)
        assert self.first_date < self.last_date

    def _update_step_flags(self) -> None:
        match self.step:
            case "normal":
                self.possible_ban = False
                self.confirmed_ban = False
            case "possible_ban":
                self.possible_ban = True
                self.confirmed_ban = False
            case "confirmed_ban":
                self.possible_ban = True
                self.confirmed_ban = True
            case _:
                raise ValueError(f"Invalid step: {self.step}")

    def set_step(
        self, step: Literal["normal", "possible_ban", "confirmed_ban"]
    ) -> None:
        self.step = step
        self._update_step_flags()

    def reset_for_new_day(self, max_days: int) -> None:
        self.set_step("normal")
        self.update_date(days=max_days, infinity=True)
        self.player_id = 0


async def produce_players(
    players: list[PlayerStruct],
    player_queue: Queue[ToScrapeStruct],
):
    if not players:
        return

    wide_event.add({"queue_players": {"count": len(players)}})
    metadata = MetaData(version=1, source="scrape_task_producer")
    player_structs = [
        ToScrapeStruct(metadata=metadata, player_data=player)
        for player in players
        if len(player.name) <= 13
    ]
    if not player_structs:
        return
    error = await player_queue.put(player_structs)
    if isinstance(error, Exception):
        raise error


def _reduce_days(fetch_params: FetchParams) -> FetchParams:
    wide_event.add({"reduce_days": {"fetch_params": asdict(fetch_params)}})
    _days = fetch_params.days - 1 if fetch_params.days > 1 else 1
    fetch_params.update_date(days=_days)
    fetch_params.player_id = 0
    return fetch_params


def determine_fetch_params(
    fetch_params: FetchParams,
    players: list[PlayerStruct] | None,
    max_days: int = 20,
    max_possible_ban_days: int = 7,
    max_confirmed_ban_days: int = 14,
):
    if players is None:
        return fetch_params

    fetch_params._update_step_flags()

    if len(players) >= fetch_params.limit:
        fetch_params.player_id = players[-1].id
        return fetch_params

    match fetch_params.step:
        case "normal":
            if fetch_params.days > 1:
                return _reduce_days(fetch_params)

            assert fetch_params.days <= 1
            wide_event.add(
                {"set_step": {"from": fetch_params.step, "to": "confirmed_ban"}}
            )
            _force_log()
            fetch_params.set_step("possible_ban")
            fetch_params.update_date(days=max_days, infinity=True)
            return fetch_params

        case "possible_ban":
            if fetch_params.days > max_possible_ban_days:
                return _reduce_days(fetch_params)

            assert fetch_params.days <= max_possible_ban_days
            wide_event.add(
                {"set_step": {"from": fetch_params.step, "to": "confirmed_ban"}}
            )
            _force_log()
            fetch_params.set_step("confirmed_ban")
            fetch_params.update_date(days=max_days, infinity=True)
            return fetch_params

        case "confirmed_ban":
            if fetch_params.days > max_confirmed_ban_days:
                return _reduce_days(fetch_params)

            assert fetch_params.days <= max_confirmed_ban_days
            wide_event.add(
                {"set_step": {"from": fetch_params.step, "to": "confirmed_ban"}}
            )
            _force_log()
            fetch_params.set_step("normal")
            fetch_params.update_date(days=max_days, infinity=True)
            fetch_params.done = True
            return fetch_params


async def process_players(
    async_session: async_sessionmaker[AsyncSession],
    player_repo: PlayerRepo,
    player_queue: Queue[ToScrapeStruct],
    limit: int = 10,
):
    max_days = 20
    fp = FetchParams(
        step="normal",
        days=max_days,
        player_id=0,
        limit=limit,
    )

    last_day = date.today()

    while True:
        token = wide_event.set({})
        try:
            lag = await player_queue.lag()
            if last_day != date.today():
                wide_event.add({"new_day_reset": True})
                _force_log()
                last_day = date.today()
                fp.reset_for_new_day(max_days)

            if lag >= 100_000:
                wide_event.add({"lag_throttle": {"lag": lag}})
                await asyncio.sleep(10)
                continue

            fp_dict = asdict(fp)
            fp_dict.update(
                {"first_date": str(fp.first_date), "last_date": str(fp.last_date)}
            )
            wide_event.add({"fetch_params": fp_dict})

            async with async_session() as session:
                players = await player_repo.select_player(
                    async_session=session,
                    player_id=fp.player_id,
                    possible_ban=fp.possible_ban,
                    confirmed_ban=fp.confirmed_ban,
                    or_none=fp.step == "normal",
                    first_date=fp.first_date,
                    last_date=fp.last_date,
                    limit=fp.limit,
                )

            await produce_players(players=players, player_queue=player_queue)

            fp = determine_fetch_params(
                fetch_params=fp,
                players=players,
                max_days=max_days,
            )

            if fp.done:
                fp.done = False
                now = datetime.now()
                end_of_today = datetime.combine(now.date(), time.max)

                time_remaining = end_of_today - now
                sleep_time = int(time_remaining.total_seconds())
                sleep_time = max(sleep_time, 1)  # Ensure at least 1 second sleep
                wide_event.add({"done_for_day": {"sleep_seconds": sleep_time}})
                _force_log()
                await asyncio.sleep(sleep_time)
        except Exception as exc:
            wide_event.add({"error": {"message": str(exc)}})
            raise
        finally:
            final_ctx = wide_event.get()
            force_log = bool(final_ctx.pop("force_log", False))
            if "error" in final_ctx:
                logger.error(final_ctx)
            elif force_log:
                final_ctx.update({"log_reason": "force"})
                logger.info(final_ctx)
            elif wide_event.sample():
                final_ctx.update({"log_reason": "sample"})
                logger.info(final_ctx)
            wide_event.reset(token)


async def main():
    async_session, async_engine = get_session_factory(SETTINGS=DBSettings())

    bootstrap_servers = KafkaSettings().KAFKA_BOOTSTRAP_SERVERS
    queue = QueueFactory.create_queue(
        model=ToScrapeStruct,
        queue_type="queue",
        backend_type="kafka",
        config=KafkaConfig(
            topic="players.to_scrape",
            bootstrap_servers=bootstrap_servers,
            producer=True,
            consumer=True,
            producer_config=KafkaProducerConfig(
                partition_key_fn=lambda message: str(message.player_data.id % 10)
            ),
            consumer_config=KafkaConsumerConfig(group_id="scraper"),
        ),
    )
    if isinstance(queue, Exception):
        raise queue
    player_queue = queue

    await player_queue.start()

    try:
        await process_players(
            async_session=async_session,
            player_repo=PlayerRepo(),
            player_queue=player_queue,
            limit=Settings().LIMIT,
        )
    finally:
        await async_engine.dispose()
        await player_queue.stop()


async def run_async():
    await main()


def run():
    asyncio.run(run_async())


if __name__ == "__main__":
    run()
