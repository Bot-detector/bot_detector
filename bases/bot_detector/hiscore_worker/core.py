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
    sql = sqla.insert(dbHighscoreData).values([d.model_dump() for d in data])
    async with Session.begin() as session:
        await session.execute()


async def process_data(queue: Queue, error_queue=Queue):
    while True:
        batch: list[ConsumerRecord] = await queue.get()
        batched: list[ScraperData] = [ScraperData(**m.value) for m in batch]
        del batch  # saving some memory

        print(batched[0])
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
