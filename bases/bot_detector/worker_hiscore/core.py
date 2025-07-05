import asyncio
import logging
import traceback

from bot_detector import database as db
from bot_detector.database import Settings as DBSettings
from bot_detector.database.repositories import HighscoreDataRepo, PlayerRepo
from bot_detector.kafka import Settings as KafkaSettings
from bot_detector.kafka.repositories import (
    RepoPlayerScrapedConsumer,
    RepoPlayerScrapedProducer,
)
from bot_detector.structs import ScrapedStruct
from pydantic_settings import BaseSettings
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    N_WORKERS: int = 1
    MAX_BATCH_SIZE: int = 10_000
    MAX_INTERVAL_MS: int = 5_000


async def insert_batch(
    session_factory: async_sessionmaker[AsyncSession],
    batch: list[ScrapedStruct],
    highscore_repo: HighscoreDataRepo,
    player_repo: PlayerRepo,
) -> tuple[None, str | None]:
    logger.debug(f"batch inserting: {len(batch)}")
    # extract player and highscore data
    player_batch = [d.player_data for d in batch]
    highscore_batch = [d.highscore_data for d in batch if d.highscore_data is not None]

    try:
        async with session_factory() as session:
            async with session.begin():
                await player_repo.update_many_players(
                    async_session=session,
                    players_data=player_batch,
                )
                await highscore_repo.insert_highscore_many(
                    async_session=session,
                    highscore_data=highscore_batch,
                )
                await session.commit()
    except OperationalError as e:
        return None, str(e)

    logger.debug(f"inserted: {len(batch)}")
    return None, None


async def consume_many_task(
    worker_id: int,
    max_messages: int,
    max_interval_ms: int,
    player_sc_consumer: RepoPlayerScrapedConsumer,
    player_sc_producer: RepoPlayerScrapedProducer,
    highscore_repo: HighscoreDataRepo,
    player_repo: PlayerRepo,
    session_factory: async_sessionmaker[AsyncSession],
):
    while True:
        try:
            batch, errors = await player_sc_consumer.consume_many(
                max_messages=max_messages,
                timeout_ms=max_interval_ms,
            )
            logger.info(f"[{worker_id}] consumed {len(batch)} scrapes")

            if errors:
                logger.error(f"[{worker_id}] Errors during consumption: {errors}")

            if not batch:
                logger.info("No highscore data to process.")
                await asyncio.sleep(15)
                continue

            if len(batch) < max_messages:
                await asyncio.sleep(15)

            _, error = await insert_batch(
                highscore_repo=highscore_repo,
                player_repo=player_repo,
                batch=batch,
                session_factory=session_factory,
            )

            if error:
                logger.error(f"{error}")
                await asyncio.gather(
                    *[player_sc_producer.produce_one(b) for b in batch]
                )
                await asyncio.sleep(15)

            await player_sc_consumer.commit()
        except Exception as e:
            logger.error(f"[{worker_id}] Error consuming scrapes: {e}")
            logger.debug(f"[{worker_id}] Traceback: \n{traceback.format_exc()}")
            await asyncio.gather(*[player_sc_producer.produce_one(b) for b in batch])
            await asyncio.sleep(15)


async def main():
    session_factory, async_engine = db.get_session_factory(SETTINGS=DBSettings())

    player_repo = PlayerRepo()
    highscore_repo = HighscoreDataRepo()

    ## consumer
    player_sc_consumer = RepoPlayerScrapedConsumer(
        bootstrap_servers=KafkaSettings().KAFKA_BOOTSTRAP_SERVERS,
        group_id="highscore_worker",
    )
    ## producer
    player_sc_producer = RepoPlayerScrapedProducer(
        bootstrap_servers=KafkaSettings().KAFKA_BOOTSTRAP_SERVERS,
    )

    # start kafka producers and consumers
    await player_sc_consumer.start()
    await player_sc_producer.start()

    # start workers
    workers = [
        asyncio.create_task(
            consume_many_task(
                worker_id=worker_id,
                max_messages=Settings().MAX_BATCH_SIZE,
                max_interval_ms=Settings().MAX_INTERVAL_MS,
                player_sc_consumer=player_sc_consumer,
                player_sc_producer=player_sc_producer,
                highscore_repo=highscore_repo,
                player_repo=player_repo,
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
