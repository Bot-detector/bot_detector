import asyncio
import logging
from datetime import timedelta
from typing import Literal

from bot_detector import database as db
from bot_detector.database import Settings as DBSettings
from bot_detector.database.repositories import (
    HighscoreDataDailyRepo,
    HighscoreDataMonthlyRepo,
    HighscoreDataWeeklyRepo,
    PlayerRepo,
)
from bot_detector.kafka import Settings as KafkaSettings
from bot_detector.kafka.repositories import (
    RepoPlayerScrapedConsumer,
    RepoPlayerScrapedProducer,
)
from bot_detector.structs import HighscoreBaseStruct, ScrapedStruct
from pydantic import ValidationError
from pydantic_settings import BaseSettings
from sqlalchemy.exc import IntegrityError, TimeoutError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    N_WORKERS: int = 1


def set_ttl(
    data: HighscoreBaseStruct, table: Literal["daily", "weekly", "monthly"]
) -> HighscoreBaseStruct:
    """objective is to more or less keep 30 records"""
    _data = data.model_copy()

    match table:
        case "daily":
            _data.time_to_live = _data.scrape_date + timedelta(days=30)
        case "weekly":
            weeks = 26  # 6 months
            _data.time_to_live = _data.scrape_date + timedelta(days=weeks * 7)
        case "monthly":
            months = 24
            _data.time_to_live = _data.scrape_date + timedelta(days=months * 30)
    return _data


async def process_data(
    session_factory: async_sessionmaker[AsyncSession],
    scraped_data: ScrapedStruct,
    player_repo: PlayerRepo,
    hs_repo_daily: HighscoreDataDailyRepo,
    hs_repo_weekly: HighscoreDataWeeklyRepo,
    hs_repo_monthly: HighscoreDataMonthlyRepo,
):
    # extract player and highscore data
    player_data = scraped_data.player_data
    hs_data = scraped_data.highscore_data

    async with session_factory() as session:
        async with session.begin():
            await player_repo.update_player(
                async_session=session, player_data=player_data
            )

            if hs_data is not None:
                hs_daily = set_ttl(data=hs_data, table="daily")
                hs_weekly = set_ttl(data=hs_data, table="weekly")
                hs_monthly = set_ttl(data=hs_data, table="monthly")

                # extreme4all: this is a lazy way to insert into the other tables,
                # it does mean alot of insert.on_duplicate_key_update()
                await hs_repo_daily.insert_highscore(
                    async_session=session, highscore_data=hs_daily
                )
                await hs_repo_weekly.insert_highscore(
                    async_session=session, highscore_data=hs_weekly
                )
                await hs_repo_monthly.insert_highscore(
                    async_session=session, highscore_data=hs_monthly
                )
            await session.commit()


async def work(
    worker_id: int,
    player_sc_consumer: RepoPlayerScrapedConsumer,
    player_sc_producer: RepoPlayerScrapedProducer,
    session_factory: async_sessionmaker[AsyncSession],
):
    while True:
        # consume messages from Kafka
        try:
            scraped_data = await player_sc_consumer.consume_one()
        except ValidationError as e:
            error = e.json()
            logger.error(error)
            continue

        # handle exceptions
        if scraped_data is None:
            logger.error(f"[{worker_id}]: No data is available.")
            await asyncio.sleep(10)
            continue

        # data validation, if for name is too long, skip
        # can happen for anonymous players (anonymoususer-abcdefgh-ijkl-mnop-qrst-uvwxyz123456)
        if len(scraped_data.player_data.name) > 13:
            continue

        # insert data into the database
        try:
            await process_data(
                session_factory=session_factory,
                scraped_data=scraped_data,
                player_repo=PlayerRepo(),
                hs_repo_daily=HighscoreDataDailyRepo(),
                hs_repo_weekly=HighscoreDataWeeklyRepo(),
                hs_repo_monthly=HighscoreDataMonthlyRepo(),
            )
        except IntegrityError as e:
            logger.warning(f"[{worker_id}]: {e=}")
            await player_sc_producer.produce_one(scraped_data=scraped_data)
            continue
        except TimeoutError as e:
            logger.warning(f"[{worker_id}]: {e=}")
            await player_sc_producer.produce_one(scraped_data=scraped_data)
            continue

        logger.info(f"[{worker_id}][{scraped_data.player_data.name}]: upserted.")


async def main():
    session_factory, async_engine = db.get_session_factory(SETTINGS=DBSettings())

    # initialize kafka producers and consumers
    b_server = KafkaSettings().KAFKA_BOOTSTRAP_SERVERS
    ## consumer
    player_sc_consumer = RepoPlayerScrapedConsumer(
        bootstrap_servers=b_server, group_id="highscore_worker"
    )
    ## producer
    player_sc_producer = RepoPlayerScrapedProducer(bootstrap_servers=b_server)

    # start kafka producers and consumers
    await player_sc_consumer.start()
    await player_sc_producer.start()

    # start workers
    workers = [
        asyncio.create_task(
            work(
                worker_id=worker_id,
                player_sc_consumer=player_sc_consumer,
                player_sc_producer=player_sc_producer,
                session_factory=session_factory,
            )
        )
        for worker_id in range(Settings().N_WORKERS)
    ]
    await asyncio.gather(*workers)
    await async_engine.dispose()


async def run_async():
    await main()


def run():
    asyncio.run(run_async())


if __name__ == "__main__":
    run()
