import asyncio
import logging
import time
import traceback
from asyncio import Queue

from bot_detector import database as db
from bot_detector.database import Settings as DBSettings
from bot_detector.database.repositories import ReportRepo
from bot_detector.kafka import Settings as KafkaSettings
from bot_detector.kafka.repositories import (
    RepoReportsToInsertConsumer,
    RepoReportsToInsertProducer,
)
from bot_detector.structs import ParsedDetection, ReportsToInsertStruct
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


class InvalidReport(Exception): ...


async def add_to_report_queue(report: ReportsToInsertStruct, queue: Queue):
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


async def get_report_queue(queue: Queue) -> ReportsToInsertStruct | None:
    if queue.empty():
        await asyncio.sleep(1)
        return

    report = await queue.get()
    queue.task_done()

    if not isinstance(report, ReportsToInsertStruct):
        logger.warning(
            {
                "msg": "invalid report",
                "expected": "ReportsToInsertStruct",
                "received": report.__class__,
            }
        )
        return
    return report


async def get_batch_queue(queue: Queue) -> list[ReportsToInsertStruct]:
    batch = await queue.get()
    queue.task_done()

    valid_items = []
    for item in batch:
        if isinstance(item, ReportsToInsertStruct):
            valid_items.append(item)
        else:
            logger.warning(
                {
                    "msg": "invalid report",
                    "expected": "ReportsToInsertStruct",
                    "received": item.__class__,
                }
            )

    return valid_items


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


def add_to_batch(
    batch: list, report: ReportsToInsertStruct
) -> list[ReportsToInsertStruct]:
    if not isinstance(report, ReportsToInsertStruct):
        logger.warning(
            {
                "msg": "invalid report",
                "expected": "ReportsToInsertStruct",
                "received": report.__class__,
            }
        )
        return batch

    batch.append(report)
    return batch


async def update_batch_queue(
    batch: list,
    _time: float,
    max_interval: int,
    batch_queue: Queue,
    max_batch_size: int,
) -> tuple[list, float]:
    delta = time.time() - _time
    if len(batch) == max_batch_size or delta > max_interval:
        await batch_queue.put(batch)
        return [], time.time()
    logger.debug(f"{len(batch)=}, {max_batch_size=}, {delta=}, {max_interval=}")
    return batch, _time


async def batch_task(
    max_batch_size: int,
    batch_queue: Queue,
    report_queue: Queue,
    max_interval=60,
):
    """
    collects reports from a report queue, batches them, and sends the batches to a batch queue.
    Args:
        max_batch_size (int): The maximum number of reports in a single batch before sending.
        batch_queue (Queue): The queue to which completed batches are sent.
        report_queue (Queue): The queue from which individual reports are received.
        max_interval (int, optional): The maximum time interval (in seconds) to wait before sending a batch, even if it is not full. Defaults to 60.
    Behavior:
        - Continuously retrieves reports from the report_queue.
        - Adds each report to the current batch.
        - Sends the batch to batch_queue when either max_batch_size is reached or max_interval seconds have passed since the last batch was sent.
        - Marks each report as done in the report_queue after processing.
    Note:
        This function is designed to be run as an asyncio task.
    """
    batch, _time = [], time.time()
    while True:
        report = await get_report_queue(queue=report_queue)
        if report:
            logger.debug(
                {
                    "msg": "adding to batch",
                    "reporter_id": report.report.reporter_id,
                    "reported_id": report.report.reported_id,
                }
            )
            batch = add_to_batch(batch=batch, report=report)

        batch, _time = await update_batch_queue(
            batch=batch,
            batch_queue=batch_queue,
            max_batch_size=max_batch_size,
            max_interval=max_interval,
            _time=_time,
        )
        # insert_task reads batch_queue


async def insert_batch(
    report_repo: ReportRepo,
    batch: list[ParsedDetection],
    session_factory: async_sessionmaker[AsyncSession],
):
    logger.debug(f"batch inserting: {len(batch)}")
    async with session_factory() as session:
        async with session.begin():
            await report_repo.insert(async_session=session, reports=batch)
            await session.commit()
    logger.debug(f"inserted: {len(batch)}")


async def insert_task(
    report_repo: ReportRepo,
    batch_queue: Queue,
    error_queue: Queue,
    session_factory: async_sessionmaker[AsyncSession],
):
    """
    Continuously processes batches of tasks from the batch_queue, attempts to insert each batch into the report repository,
    and handles errors by logging and re-queuing failed batches to the error_queue.
    Args:
        report_repo (ReportRepo): The repository instance used to insert report batches.
        batch_queue (Queue): An asyncio queue from which batches of tasks are retrieved for processing.
        error_queue (Queue): An asyncio queue to which failed batches are added for further handling.
    Behavior:
        - Retrieves batches from batch_queue in an infinite loop.
        - Attempts to insert each batch into the report repository.
        - On OperationalError or any other Exception, logs the error, re-queues the batch to error_queue, and sleeps before retrying.
    Note:
        This function is designed to be run as an asyncio task.
    """

    while True:
        batch = await get_batch_queue(queue=batch_queue)
        if len(batch) == 0:
            continue
        try:
            batch_pared_detection = [r.report for r in batch]
            await insert_batch(
                report_repo=report_repo,
                batch=batch_pared_detection,
                session_factory=session_factory,
            )
        except OperationalError as e:
            logger.error({"error": e})
            await asyncio.gather(
                *[add_to_error_queue(report=r, queue=error_queue) for r in batch]
            )
            await asyncio.sleep(5)
        except Exception as e:
            logger.error({"error": e})
            logger.debug(f"Traceback: \n{traceback.format_exc()}")
            await asyncio.gather(
                *[add_to_error_queue(report=r, queue=error_queue) for r in batch]
            )
            await asyncio.sleep(5)


async def consume_task(
    report_consumer: RepoReportsToInsertConsumer, report_queue: Queue
) -> None:
    """
    Continuously consumes reports from a Kafka queue using the provided consumer, validates them,
    and adds valid reports of version 1 to the provided asyncio queue for further processing.

    Args:
        report_consumer (RepoReportsToInsertConsumer): The consumer instance to fetch reports from Kafka.
        report_queue (Queue): The asyncio queue to which valid reports will be added.

    Notes:
        - Only reports with metadata version 1 are added to the queue.
        - Validation errors are logged and skipped.
        - The function runs indefinitely until externally stopped.
    """
    while True:
        # read message from kafka queue
        try:
            report = await report_consumer.consume_one()

            logger.debug(
                {
                    "msg": "consumed_report",
                    "reporter_id": report.report.reporter_id,
                    "reported_id": report.report.reported_id,
                }
            )
        except ValidationError as e:
            error = e.json()
            logger.error(error)
            continue

        # transform if needed
        if report.metadata.version == 1:
            # add message to asyncio Queue
            await add_to_report_queue(report=report, queue=report_queue)
            # batch_task will read the report_queue
        else:
            logger.warning(f"invalide version: {report=}")


async def error_task(error_queue: Queue, report_producer: RepoReportsToInsertProducer):
    while True:
        report: ReportsToInsertStruct = await error_queue.get()
        if not isinstance(report, ReportsToInsertStruct):
            logger.warning(f"invalid {report=}")
            continue
        await report_producer.produce_one(report=report)


async def main():
    session_factory, async_engine = db.get_session_factory(SETTINGS=DBSettings())
    report_repo = ReportRepo()
    MAX_BATCH_SIZE = 1_000  # maybe env variable?
    MAX_INTERVAL = 60

    report_queue = Queue(maxsize=100)
    batch_queue = Queue(maxsize=10)
    error_queue = Queue()

    # initialize kafka producers and consumers
    b_server = KafkaSettings().KAFKA_BOOTSTRAP_SERVERS
    ## consumer
    report_consumer = RepoReportsToInsertConsumer(
        bootstrap_servers=b_server,
        group_id="report_worker",
    )

    ## producer
    report_producer = RepoReportsToInsertProducer(
        bootstrap_servers=b_server,
    )

    # start kafka producers and consumers
    await report_consumer.start()
    await report_producer.start()

    # start tasks
    tasks = [
        asyncio.create_task(
            consume_task(report_consumer=report_consumer, report_queue=report_queue)
        ),
        asyncio.create_task(
            batch_task(
                max_interval=MAX_INTERVAL,
                max_batch_size=MAX_BATCH_SIZE,
                batch_queue=batch_queue,
                report_queue=report_queue,
            )
        ),
        asyncio.create_task(
            insert_task(
                report_repo=report_repo,
                batch_queue=batch_queue,
                error_queue=error_queue,
                session_factory=session_factory,
            )
        ),
        asyncio.create_task(
            error_task(
                error_queue=error_queue,
                report_producer=report_producer,
            )
        ),
    ]
    await asyncio.gather(*tasks)


async def run_async():
    await main()


def run():
    asyncio.run(run_async())


if __name__ == "__main__":
    run()
