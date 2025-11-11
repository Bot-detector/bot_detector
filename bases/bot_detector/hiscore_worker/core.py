import asyncio
import logging

from bot_detector import database as db
from bot_detector.database import Settings as DBSettings
from bot_detector.highscore_worker import HighscoreWorkerService
from bot_detector.kafka import Settings as KafkaSettings
from bot_detector.kafka.repositories import (
    RepoPlayerScrapedConsumer,
    RepoPlayerScrapedProducer,
)
from bot_detector.structs import ScrapedStruct
from pydantic import ValidationError
from pydantic_settings import BaseSettings
from sqlalchemy.exc import IntegrityError, TimeoutError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    N_WORKERS: int = 1


async def work(
    worker_id: int,
    player_sc_consumer: RepoPlayerScrapedConsumer,
    player_sc_producer: RepoPlayerScrapedProducer,
    session_factory: async_sessionmaker[AsyncSession],
    worker_service: HighscoreWorkerService,
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

        if worker_service.should_skip(scraped_data):
            continue

        # insert data into the database
        try:
            await worker_service.persist_scraped_data(
                session_factory=session_factory,
                scraped_data=scraped_data,
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
    worker_service = HighscoreWorkerService()

    # initialize kafka producers and consumers
    b_server = KafkaSettings().KAFKA_BOOTSTRAP_SERVERS
    ## consumer
    player_sc_consumer = RepoPlayerScrapedConsumer(
        bootstrap_servers=b_server,
        group_id="highscore_worker",
    )
    ## producer
    player_sc_producer = RepoPlayerScrapedProducer(
        bootstrap_servers=b_server,
    )

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
                worker_service=worker_service,
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
