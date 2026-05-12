import asyncio
import logging

from bot_detector import database as db
from bot_detector.database import Settings as DBSettings
from bot_detector.database.hiscore import HighscoreDataRepo
from bot_detector.database.player import PlayerRepo
from bot_detector.event_queue.adapters.kafka import (
    KafkaConfig,
    KafkaConsumerConfig,
    KafkaProducerConfig,
    KafkaSettings,
)
from bot_detector.event_queue.core import QueueProducer
from bot_detector.event_queue.factory import QueueFactory
from bot_detector.event_queue.structs import (
    DataToPredictStruct,
    ScrapedStruct,
)
from bot_detector.worker.core import WorkerRunner

from .settings import Settings
from .worker import HiscoreWorker

logger = logging.getLogger(__name__)

SETTINGS = Settings()
KAFKA_SETTINGS = KafkaSettings()


def partition_key_fn(msg: ScrapedStruct) -> str:
    return str(msg.player_data.id % 10)


async def get_data_to_predict_producer() -> QueueProducer[DataToPredictStruct]:
    data_to_predict_producer = QueueFactory.create_queue(
        model=DataToPredictStruct,
        queue_type="producer",
        backend_type="kafka",
        config=KafkaConfig(
            topic="data.to_predict",
            bootstrap_servers=KAFKA_SETTINGS.bootstrap_servers,
            producer=True,
            producer_config=KafkaProducerConfig(partition_key_fn=partition_key_fn),
        ),
    )

    if isinstance(data_to_predict_producer, Exception):
        raise data_to_predict_producer

    assert isinstance(data_to_predict_producer, QueueProducer)
    await data_to_predict_producer.start()
    return data_to_predict_producer


async def main():
    session_factory, async_engine = db.get_session_factory(SETTINGS=DBSettings())

    player_repo = PlayerRepo()
    highscore_repo = HighscoreDataRepo()

    data_to_predict_producer = await get_data_to_predict_producer()

    tasks = []
    for worker_id in range(SETTINGS.N_WORKERS):
        worker = HiscoreWorker(
            worker_id=worker_id,
            session_factory=session_factory,
            highscore_repo=highscore_repo,
            player_repo=player_repo,
            data_to_predict_producer=data_to_predict_producer,
        )
        kafka_config = KafkaConfig(
            topic="players.scraped",
            bootstrap_servers=KAFKA_SETTINGS.bootstrap_servers,
            producer=True,
            consumer=True,
            producer_config=KafkaProducerConfig(partition_key_fn=partition_key_fn),
            consumer_config=KafkaConsumerConfig(
                group_id="highscore_worker",
                consume_timeout_ms=SETTINGS.MAX_INTERVAL_MS,
            ),
        )
        runner = WorkerRunner(
            worker=worker,
            config=kafka_config,
            model=ScrapedStruct,
            batch_size=SETTINGS.MAX_BATCH_SIZE,
        )
        task = asyncio.create_task(runner.run())
        tasks.append(task)

    try:
        await asyncio.gather(*tasks)
    finally:
        await async_engine.dispose()
        await data_to_predict_producer.stop()
        await runner._queue.stop()


async def run_async():
    await main()


def run():
    asyncio.run(run_async())


if __name__ == "__main__":
    run()
