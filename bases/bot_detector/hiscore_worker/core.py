import asyncio
from asyncio import Queue

from bot_detector import database as db
from bot_detector.kafka_client import KafkaConsumer, KafkaProducer
from pydantic_settings import BaseSettings

from . import worker


class Settings(BaseSettings):
    PROXY_API_KEY: str
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9094"
    BATCH_SIZE: int = 2


async def main():
    SETTINGS = Settings()
    DB_SETTINGS = db.Settings()
    session_factory, async_engine = db.get_session_factory(SETTINGS=DB_SETTINGS)

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
            worker.process_data(
                queue=scraped_queue,
                error_queue=error_queue,
                async_session=session_factory,
            )
        ),
    ]
    await asyncio.gather(*kafka_tasks)

    await consumer.engine.stop()
    await producer.engine.stop()

    await async_engine.dispose()


def run():
    asyncio.run(main())


if __name__ == "__main__":
    run()
