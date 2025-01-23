import asyncio
import json
from asyncio import Queue

import sqlalchemy

# import sqlalchemy as sqla
from aiokafka import ConsumerRecord
from bot_detector.database import Session
from bot_detector.kafka_client import KafkaConsumer, KafkaProducer
from bot_detector.schema import HighscoreData, ScraperData
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROXY_API_KEY: str
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9094"
    BATCH_SIZE: int = 2


async def batch_insert(data: list[HighscoreData]):
    # Step 1: Construct the insert statement
    sql_insert = sqlalchemy.text("""
    INSERT INTO highscore_data (player_id, scrape_ts, skills, activities) 
    VALUES (:player_id, :scrape_ts, :skills, :activities) AS new
    ON DUPLICATE KEY UPDATE
        scrape_ts = CASE
            WHEN highscore_data.scrape_ts < new.scrape_ts THEN new.scrape_ts
            ELSE highscore_data.scrape_ts
        END,
        skills = CASE
            WHEN highscore_data.scrape_ts < new.scrape_ts THEN new.skills
            ELSE highscore_data.skills
        END,
        activities = CASE
            WHEN highscore_data.scrape_ts < new.scrape_ts THEN new.activities
            ELSE highscore_data.activities
        END
    """)

    # Step2: Transform the data into dictionaries for parameterized insertion
    data_to_insert = [
        {
            "player_id": d.player_id,
            "scrape_ts": d.scrape_ts,
            "skills": json.dumps(d.skills),  # Serialize skills as JSON
            "activities": json.dumps(d.activities),  # Serialize activities as JSON
        }
        for d in data
    ]
    # Step 3: Execute the insert statement
    async with Session.begin() as session:
        await session.execute(sql_insert, data_to_insert)


async def process_data(queue: Queue, error_queue=Queue):
    while True:
        batch: list[ConsumerRecord] = await queue.get()
        batched: list[ScraperData] = [ScraperData(**m.value) for m in batch]
        del batch  # saving some memory

        hs_data: list[HighscoreData] = []
        for msg in batched:
            if msg.hiscore_data is None:
                continue

            # we need to avoid duplicate player_id:year:week
            data = HighscoreData(
                player_id=msg.player_data.id,
                scrape_ts=msg.player_data.updated_at,
                skills=msg.hiscore_data.skills,
                activities=msg.hiscore_data.activities,
            )

            can_append = True
            idx_to_remove = list()

            for idx, d in enumerate(hs_data):
                if d.player_id != data.player_id:
                    continue

                d_year = d.scrape_ts.isocalendar().year
                if d_year != data.scrape_ts.isocalendar().year:
                    continue

                d_week = d.scrape_ts.isocalendar().week
                if d_week != data.scrape_ts.isocalendar().week:
                    continue

                if d.scrape_ts < data.scrape_ts:
                    idx_to_remove.append(idx)
                    continue

                if d.scrape_ts > data.scrape_ts:
                    print(f"existing: {d.scrape_ts} > new: {data.scrape_ts}")
                    can_append = False
                    break

            for idx in idx_to_remove:
                print(f"removing: {idx}")
                hs_data.pop(idx)

            if can_append:
                hs_data.append(data)
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
            batch_size=SETTINGS.BATCH_SIZE,
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
