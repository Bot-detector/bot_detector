import asyncio
import logging

from bot_detector import database as db
from bot_detector.database import Settings as DBSettings
from bot_detector.database.repositories import HighscoreDataDailyRepo, PlayerRepo
from bot_detector.kafka import Settings as KafkaSettings
from bot_detector.kafka.repositories import (
    RepoPlayerScrapedConsumer,
    RepoPlayerScrapedProducer,
)
from bot_detector.structs import HighscoreDataDailyStruct, ScrapedStruct
from pydantic import ValidationError
from pydantic_settings import BaseSettings
from sqlalchemy.exc import IntegrityError, TimeoutError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    N_WORKERS: int = 1


async def process_data(
    session_factory: async_sessionmaker[AsyncSession],
    scraped_data: ScrapedStruct,
):
    # initialize repositories
    player_repo = PlayerRepo()
    highscore_repo = HighscoreDataDailyRepo()

    # extract player and highscore data
    player_data = scraped_data.player_data
    highscore_data = scraped_data.highscore_data

    async with session_factory() as session:
        async with session.begin():
            await player_repo.update_player(
                async_session=session, player_data=player_data
            )

            if highscore_data is not None:
                await highscore_repo.insert_highscore(
                    async_session=session, highscore_data=highscore_data
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

        # insert data into the database
        try:
            await process_data(
                session_factory=session_factory, scraped_data=scraped_data
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


async def run_async():
    await main()


def run():
    asyncio.run(run_async())


if __name__ == "__main__":
    run()
