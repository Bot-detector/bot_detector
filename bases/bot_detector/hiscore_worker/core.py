import asyncio
from asyncio import Queue

import sqlalchemy as sqla
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
    sql_temp = sqla.text("""
        CREATE TABLE `temp_hs_data` (
        `player_id` INT NOT NULL,
        `scrape_ts` DATETIME NOT NULL,
        `start_ts` DATETIME NOT NULL,
        `scrape_year` INT AS (YEAR(scrape_ts)) STORED,
        `scrape_week` INT AS (WEEK(scrape_ts, 3)) STORED,
        `skills` JSON DEFAULT NULL,
        `activities` JSON DEFAULT NULL,
        PRIMARY KEY (`player_id`, `scrape_year`, `scrape_week`),
        );
    """)
    sql_insert_temp_table = sqla.text("""
        INSERT INTO temp_hs_data (player_id, scrape_ts, skills, activities)
        VALUES (:player_id, :scrape_ts, :skills, :activities)
    """)

    sql_insert = """
        INSERT INTO highscore_data (player_id, scrape_ts, skills, activities, skills_delta, activities_delta)
        SELECT 
            tmp.player_id, 
            tmp.scrape_ts, 
            tmp.skills, 
            tmp.activities 
        FROM temp_hs_data tmp
        INNER JOIN highscore_data hsd ON (
            tmp.player_id = hsd.player_id and 
            tmp.scrape_week => hsd.scrape_week
            tmp.

        )
        ON DUPLICATE KEY UPDATE ()
    """
    sql = sqla.insert(dbHighscoreData).values([d.model_dump() for d in data])
    async with Session.begin() as session:
        await session.execute(sql_temp)
        await session.execute(sql_insert_temp_table, params=data_to_insert)


async def process_data(queue: Queue, error_queue=Queue):
    while True:
        batch: list[ConsumerRecord] = await queue.get()
        batched: list[ScraperData] = [ScraperData(**m.value) for m in batch]
        del batch  # saving some memory

        parsed_batch = []
        for msg in batched:
            HighscoreData()
        break


async def main():
    global SETTINGS
    SETTINGS = Settings()

    scraped_queue = Queue()
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
            batch_size=1000,
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
