import asyncio
from asyncio import Queue

import sqlalchemy
import sqlalchemy.dialects.mysql as sqla

# import sqlalchemy as sqla
from aiokafka import ConsumerRecord
from bot_detector.database import Session
from bot_detector.database.models import dbHighscoreData
from bot_detector.kafka_client import KafkaConsumer, KafkaProducer
from bot_detector.schema import HighscoreData, ScraperData
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROXY_API_KEY: str
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9094"


async def batch_insert(data: list[HighscoreData]):
    data_to_insert = [
        {
            "player_id": d.player_id,
            "scrape_ts": d.scrape_ts,
            "skills": d.skills,
            "activities": d.activities,
        }
        for d in data
    ]

    # Step 1: Construct the insert statement
    sql_insert = sqla.insert(dbHighscoreData).values(data_to_insert)

    # Step 2: Add ON DUPLICATE KEY UPDATE with conditional logic using SQLAlchemy case
    sql_insert = sql_insert.on_duplicate_key_update(
        scrape_ts=sqlalchemy.case(
            (
                dbHighscoreData.scrape_ts < sqlalchemy.bindparam("scrape_ts"),
                sqlalchemy.bindparam("scrape_ts"),
            ),
            else_=dbHighscoreData.scrape_ts,
        ),
        skills=sqlalchemy.case(
            (
                dbHighscoreData.scrape_ts < sqlalchemy.bindparam("scrape_ts"),
                sqlalchemy.bindparam("skills"),
            ),
            else_=dbHighscoreData.skills,
        ),
        activities=sqlalchemy.case(
            (
                dbHighscoreData.scrape_ts < sqlalchemy.bindparam("scrape_ts"),
                sqlalchemy.bindparam("activities"),
            ),
            else_=dbHighscoreData.activities,
        ),
    )

    # Step 3: Execute the insert statement
    async with Session.begin() as session:
        await session.execute(
            sql_insert, data_to_insert
        )  # Bind the data_to_insert correctly


async def process_data(queue: Queue, error_queue=Queue):
    while True:
        batch: list[ConsumerRecord] = await queue.get()
        batched: list[ScraperData] = [ScraperData(**m.value) for m in batch]
        del batch  # saving some memory

        hs_data = []
        for msg in batched:
            if msg.hiscore_data is None:
                continue

            hs_data.append(
                HighscoreData(
                    player_id=msg.player_data.id,
                    scrape_ts=msg.player_data.updated_at,
                    skills=msg.hiscore_data.skills,
                    activities=msg.hiscore_data.activities,
                )
            )
        await batch_insert(hs_data)


async def main():
    global SETTINGS
    SETTINGS = Settings()

    scraped_queue = Queue(maxsize=1)
    error_queue = Queue()

    # Kafka Consumers
    consumer = KafkaConsumer(
        bootstrap_servers=SETTINGS.KAFKA_BOOTSTRAP_SERVERS,
        group_id="hiscore-worker",
    )

    # Kafka Producers
    producer = KafkaProducer(
        bootstrap_servers=SETTINGS.KAFKA_BOOTSTRAP_SERVERS,
    )

    kafka_tasks = [
        await consumer.consume(
            topic="players.scraped",
            queue=scraped_queue,
            batch_size=1,
        ),
        await producer.produce(
            topic="players.scraped",
            queue=error_queue,
        ),
        asyncio.create_task(
            process_data(
                queue=scraped_queue,
                error_queue=error_queue,
            )
        ),
    ]
    await asyncio.gather(*kafka_tasks)

    await consumer.engine.stop()
    await producer.engine.stop()


if __name__ == "__main__":
    asyncio.run(main())
