import asyncio
import logging
import traceback
from asyncio import Queue

from bot_detector import database as db
from bot_detector.database import Settings as DBSettings
from bot_detector.database.report import ReportRepo
from bot_detector.event_queue.adapters.kafka import KafkaConfig, KafkaConsumerConfig
from bot_detector.event_queue.adapters.kafka import KafkaSettings
from bot_detector.event_queue.core import Queue as EventQueue
from bot_detector.event_queue.factory import QueueFactory
from bot_detector.event_queue.structs import ReportsToInsertStruct
from bot_detector.structs import ParsedDetection
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


async def add_to_error_queue(report: ReportsToInsertStruct, queue: Queue):
    if not isinstance(report, ReportsToInsertStruct):
        logger.warning(
            {
                "msg": "invalid report",
                "expected": "ReportsToInsertStruct",
                "received": report.__class__,
            }
        )
        return
    await queue.put(item=report)


async def insert_batch(
    report_repo: ReportRepo,
    batch: list[ParsedDetection],
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[None, str | None]:
    logger.debug(f"batch inserting: {len(batch)}")
    try:
        async with session_factory() as session:
            async with session.begin():
                await report_repo.insert(async_session=session, reports=batch)
                await session.commit()
    except OperationalError as e:
        return None, str(e)
    logger.info(f"inserted: {len(batch)}")
    return None, None


async def parse_detections(
    reports: list[ReportsToInsertStruct],
) -> list[ParsedDetection]:
    parsed_detections = []
    for report in reports:
        if not isinstance(report, ReportsToInsertStruct):
            logger.warning(f"Invalid report type: {report.__class__}")
            continue
        if report.metadata.version == 1:
            parsed_detections.append(report.report)
        else:
            logger.warning(f"Unsupported report version: {report.metadata.version}")
    return parsed_detections


async def consume_many_task(
    report_consumer: EventQueue[ReportsToInsertStruct],
    max_messages: int,
    max_interval_ms: int,
    session_factory: async_sessionmaker[AsyncSession],
    report_repo: ReportRepo,
    error_queue: Queue,
):
    while True:
        try:
            reports, errors = await report_consumer.consume_many(
                max_records=max_messages,
                timeout_ms=max_interval_ms,
            )
            logger.debug(f"consumed {len(reports)} reports")

            if errors:
                logger.error(f"Errors during consumption: {errors}")

            parsed_detections = await parse_detections(reports)

            if not parsed_detections:
                logger.info("No valid reports to process.")
                await asyncio.sleep(15)
                continue

            logger.debug(f"Parsed {len(parsed_detections)} valid reports.")

            _, error = await insert_batch(
                report_repo=report_repo,
                batch=parsed_detections,
                session_factory=session_factory,
            )
            if error:
                logger.error(error)
                await asyncio.gather(
                    *[add_to_error_queue(report=r, queue=error_queue) for r in reports]
                )
                await asyncio.sleep(15)
            await report_consumer.commit()
        except Exception as e:
            logger.error(f"Error consuming reports: {e}")
            logger.debug(f"Traceback: \n{traceback.format_exc()}")
            await asyncio.sleep(5)


async def error_task(
    error_queue: Queue,
    report_producer: EventQueue[ReportsToInsertStruct],
):
    while True:
        report: ReportsToInsertStruct = await error_queue.get()
        if not isinstance(report, ReportsToInsertStruct):
            logger.warning(f"invalid {report=}")
            continue
        await report_producer.produce_one(report)


async def main():
    session_factory, async_engine = db.get_session_factory(SETTINGS=DBSettings())
    report_repo = ReportRepo()
    max_batch_size = 10_000
    max_interval_ms = 1_000

    error_queue = Queue()

    b_server = KafkaSettings().KAFKA_BOOTSTRAP_SERVERS
    queue = QueueFactory.create_queue(
        model=ReportsToInsertStruct,
        queue_type="queue",
        backend_type="kafka",
        config=KafkaConfig(
            topic="reports.to_insert",
            bootstrap_servers=b_server,
            producer=True,
            consumer=True,
            consumer_config=KafkaConsumerConfig(group_id="report_worker"),
        ),
    )
    if isinstance(queue, Exception):
        raise queue
    report_queue = queue

    await report_queue.start()

    tasks = [
        asyncio.create_task(
            consume_many_task(
                report_consumer=report_queue,
                report_repo=report_repo,
                max_messages=max_batch_size,
                max_interval_ms=max_interval_ms,
                session_factory=session_factory,
                error_queue=error_queue,
            )
        ),
        asyncio.create_task(
            error_task(
                error_queue=error_queue,
                report_producer=report_queue,
            )
        ),
    ]
    await asyncio.gather(*tasks)
    await async_engine.dispose()


async def run_async():
    await main()


def run():
    asyncio.run(run_async())


if __name__ == "__main__":
    run()
