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
from bot_detector.structs import ParsedDetection
from bot_detector.worker import Worker, WorkerRunner
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


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


class ReportWorker(Worker[ReportsToInsertStruct]):
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        report_repo: ReportRepo,
    ) -> None:
        self._session_factory = session_factory
        self._report_repo = report_repo

    async def handle(self, batch: list[ReportsToInsertStruct]) -> None:
        parsed = await parse_detections(batch)
        if not parsed:
            logger.info("No valid reports to process.")
            return

        logger.debug(f"Parsed {len(parsed)} valid reports.")

        async with self._session_factory() as session:
            async with session.begin():
                await self._report_repo.insert(async_session=session, reports=parsed)
                await session.commit()

        logger.info(f"inserted: {len(parsed)}")


async def main():
    session_factory, async_engine = db.get_session_factory(SETTINGS=DBSettings())
    report_repo = ReportRepo()
    max_batch_size = 10_000
    max_interval_ms = 1_000

    worker = ReportWorker(
        session_factory=session_factory,
        report_repo=report_repo,
    )

    runner = WorkerRunner(
        config=KafkaConfig(
            topic="reports.to_insert",
            bootstrap_servers=KafkaSettings().bootstrap_servers,
            producer=True,
            consumer=True,
            producer_config=KafkaProducerConfig(partition_key_fn=None),
            consumer_config=KafkaConsumerConfig(
                group_id="report_worker",
                consume_timeout_ms=max_interval_ms,
            ),
        ),
        model=ReportsToInsertStruct,
        worker=worker,
        batch_size=max_batch_size,
        empty_batch_sleep=15.0,
        error_sleep=5.0,
    )

    await runner.run()
    await async_engine.dispose()


async def run_async():
    await main()


def run():
    asyncio.run(run_async())


if __name__ == "__main__":
    run()
