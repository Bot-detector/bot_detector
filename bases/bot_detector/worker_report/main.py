import asyncio
import logging

from bot_detector import database as db
from bot_detector.database import Settings as DBSettings
from bot_detector.database.report import ReportRepo
from bot_detector.event_queue.adapters.kafka import (
    KafkaConfig,
    KafkaConsumerConfig,
    KafkaProducerConfig,
    KafkaSettings,
)
from bot_detector.event_queue.structs import ReportsToInsertStruct
from bot_detector.worker.core import WorkerRunner
from bot_detector.worker.metrics import start_metrics_server
from bot_detector.worker_report.settings import Settings
from bot_detector.worker_report.worker import ReportWorker

logger = logging.getLogger(__name__)

SETTINGS = Settings()
KAFKA_SETTINGS = KafkaSettings()


async def main():
    start_metrics_server(port=SETTINGS.METRICS_PORT)
    session_factory, async_engine = db.get_session_factory(SETTINGS=DBSettings())
    report_repo = ReportRepo()
    stop_event = asyncio.Event()
    tasks = []
    for worker_id in range(SETTINGS.N_WORKERS):
        worker = ReportWorker(
            worker_id=worker_id,
            session_factory=session_factory,
            report_repo=report_repo,
        )
        kafka_config = KafkaConfig(
            topic="reports.to_insert",
            bootstrap_servers=KAFKA_SETTINGS.bootstrap_servers,
            producer=True,
            consumer=True,
            producer_config=KafkaProducerConfig(partition_key_fn=None),
            consumer_config=KafkaConsumerConfig(
                group_id="report_worker",
                consume_timeout_ms=SETTINGS.MAX_INTERVAL_MS,
            ),
        )
        runner = WorkerRunner(
            worker=worker,
            config=kafka_config,
            model=ReportsToInsertStruct,
            batch_size=SETTINGS.MAX_BATCH_SIZE,
            stop_event=stop_event,
            worker_name="report",
        )
        task = asyncio.create_task(runner.run())
        tasks.append(task)

    try:
        await asyncio.gather(*tasks)
    finally:
        stop_event.set()
        await async_engine.dispose()


async def run_async():
    await main()


def run():
    asyncio.run(run_async())


if __name__ == "__main__":
    run()
