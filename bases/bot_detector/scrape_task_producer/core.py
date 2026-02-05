import asyncio
import logging
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta

from bot_detector.database import Settings as DBSettings
from bot_detector.database import get_session_factory
from bot_detector.database.player import PlayerRepo
from bot_detector.kafka import Settings as KafkaSettings
from bot_detector.structs import MetaData, PlayerStruct
from bot_detector.event_queue.adapters.kafka import (
    KafkaConfig,
    KafkaConsumerConfig,
    KafkaProducerConfig,
)
from bot_detector.event_queue.core import QueueConsumer, QueueProducer
from bot_detector.event_queue.factory import QueueFactory
from bot_detector.kafka import ToScrapeStruct
from pydantic_settings import BaseSettings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from typing_extensions import Literal

logger = logging.getLogger(__name__)


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

    def set_step(self, step: Literal["normal", "possible_ban", "confirmed_ban"]) -> None:
        self.step = step
        self._update_step_flags()

    def reset_for_new_day(self, max_days: int) -> None:
        self.set_step("normal")
        self.update_date(days=max_days, infinity=True)
        self.player_id = 0


async def produce_players(
    players: list[PlayerStruct],
    player_producer: QueueProducer[ToScrapeStruct],
):
    if not players:
        return

    logger.info(f"Putting {len(players)} players in queue")
    metadata = MetaData(version=1, source="scrape_task_producer")
    player_structs = [
        ToScrapeStruct(metadata=metadata, player_data=player)
        for player in players
        if len(player.name) <= 13
    ]
    if not player_structs:
        return
    error = await player_producer.put(player_structs)
    if isinstance(error, Exception):
        raise error


def _reduce_days(fetch_params: FetchParams) -> FetchParams:
    logger.info(f"Reducing days for {asdict(fetch_params)}")
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
            logger.info("All normal scraped, going to step: possible bans")
            fetch_params.set_step("possible_ban")
            fetch_params.update_date(days=max_days, infinity=True)
            return fetch_params

        case "possible_ban":
            if fetch_params.days > max_possible_ban_days:
                return _reduce_days(fetch_params)

            assert fetch_params.days <= max_possible_ban_days
            logger.info("All possible bans scraped, going to step: confirmed bans")
            fetch_params.set_step("confirmed_ban")
            fetch_params.update_date(days=max_days, infinity=True)
            return fetch_params

        case "confirmed_ban":
            if fetch_params.days > max_confirmed_ban_days:
                return _reduce_days(fetch_params)

            assert fetch_params.days <= max_confirmed_ban_days
            logger.info("All confirmed bans scraped, going to step: normal")
            fetch_params.set_step("normal")
            fetch_params.update_date(days=max_days, infinity=True)
            fetch_params.done = True
            return fetch_params


async def process_players(
    async_session: async_sessionmaker[AsyncSession],
    player_repo: PlayerRepo,
    player_producer: QueueProducer[ToScrapeStruct],
    player_consumer: QueueConsumer[ToScrapeStruct],
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
        lag = await player_consumer.lag()
        if last_day != date.today():
            logger.info("New day detected, resetting days and confirmed_ban")
            last_day = date.today()
            fp.reset_for_new_day(max_days)

        if lag >= 100_000:
            logger.info(f"{lag=} to high, sleeping(10)")
            await asyncio.sleep(10)
            continue

        logger.info(f"{asdict(fp)}")

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

        await produce_players(players=players, player_producer=player_producer)

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
            logger.info(f"Sleeping for {sleep_time} seconds until end of day")
            await asyncio.sleep(sleep_time)


async def main():
    async_session, async_engine = get_session_factory(SETTINGS=DBSettings())

    bootstrap_servers = KafkaSettings().KAFKA_BOOTSTRAP_SERVERS
    queue_producer = QueueFactory.create_queue(
        model=ToScrapeStruct,
        queue_type="producer",
        backend_type="kafka",
        config=KafkaConfig(
            topic="players.to_scrape",
            bootstrap_servers=bootstrap_servers,
            producer=True,
            consumer=False,
            producer_config=KafkaProducerConfig(
                partition_key_fn=lambda: "scrape_task_producer"
            ),
            consumer_config=None,
        ),
    )
    if isinstance(queue_producer, Exception):
        raise queue_producer
    player_producer = queue_producer

    queue_consumer = QueueFactory.create_queue(
        model=ToScrapeStruct,
        queue_type="consumer",
        backend_type="kafka",
        config=KafkaConfig(
            topic="players.to_scrape",
            bootstrap_servers=bootstrap_servers,
            producer=False,
            consumer=True,
            producer_config=None,
            consumer_config=KafkaConsumerConfig(group_id="scraper"),
        ),
    )
    if isinstance(queue_consumer, Exception):
        raise queue_consumer
    player_consumer = queue_consumer

    await player_producer.start()
    await player_consumer.start()

    try:
        await process_players(
            async_session=async_session,
            player_repo=PlayerRepo(),
            player_producer=player_producer,
            player_consumer=player_consumer,
            limit=Settings().LIMIT,
        )
    finally:
        await async_engine.dispose()
        await player_producer.stop()
        await player_consumer.stop()


async def run_async():
    await main()


def run():
    asyncio.run(run_async())


if __name__ == "__main__":
    run()
