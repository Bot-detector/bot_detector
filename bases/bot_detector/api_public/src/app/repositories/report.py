import asyncio
import logging
import time

from bot_detector.api_public.src.core.fastapi.dependencies.kafka import kafka_manager
from bot_detector.kafka.repositories.reports_to_insert import (
    RepoReportsToInsertProducer,
)
from bot_detector.structs import Detection, MetaData, ReportsToInsertStruct
from pydantic import ValidationError

logger = logging.getLogger(__name__)


class CustomError(Exception): ...


class Report:
    def __init__(self) -> None:
        pass

    def _check_data_size(self, data: list[Detection]) -> list[Detection] | None:
        return None if len(data) > 5000 else data

    def _filter_valid_time(self, data: list[Detection]) -> list[Detection]:
        current_time = int(time.time())
        min_ts = current_time - 25200  # 7 hours ago
        max_ts = current_time + 3600  # 1 hour in the future
        # [d for d in data if min_ts < d.ts < max_ts]
        output = []

        for d in data:
            if d.ts <= min_ts:
                logger.info(
                    f"invalid: {d.ts} <= {min_ts}, now={current_time}, {d.reporter}"
                )
                continue
            if d.ts >= max_ts:
                logger.info(
                    f"invalid: {d.ts} >= {max_ts}, now={current_time}, {d.reporter}"
                )
                continue
            output.append(d)

        return output

    def _check_unique_reporter(self, data: list[Detection]) -> list[Detection] | None:
        return None if len(set(d.reporter for d in data)) > 1 else data

    async def parse_data(self, data: list[Detection]) -> tuple[list[Detection], None]:
        """
        Parse and validate a list of detection data.
        """
        data = self._check_data_size(data)
        if not data:
            error = "invalid data size"
            logger.warning(error)
            return None, error

        data = self._filter_valid_time(data)
        if not data:
            error = "invalid time"
            logger.warning(error)
            return None, error

        data = self._check_unique_reporter(data)
        if not data:
            error = "invalid unique reporter"
            logger.warning(error)
            return None, error
        return data, None

    def _transform_detection(
        self, data: list[Detection]
    ) -> tuple[list[ReportsToInsertStruct], list | None]:
        reports = []
        errors = []

        for d in data:
            metadata = MetaData(version=1, source="api_public")
            try:
                report = ReportsToInsertStruct(metadata=metadata, report=d.model_dump())
                reports.append(report)
            except ValidationError as e:
                error = f"Validation error: {e.json()}"
                errors.append(error)
        return reports, errors

    async def send_to_kafka(self, data: list[Detection]) -> None:
        producer = kafka_manager.get_producer(key="reports_to_insert")
        producer: RepoReportsToInsertProducer | None

        if not producer:
            raise CustomError("Producer not found")

        tasks = []

        # Transform data to ReportsToInsertStruct
        reports, error = self._transform_detection(data)

        for report in reports:
            task = producer.produce_one(report=report)
            tasks.append(task)
            await asyncio.gather(*tasks)

        if len(error) > 0:
            error_msg = f"Received {len(error)} validation errors like this: {error[0]}"
            logger.error(error_msg)
            raise CustomError(error_msg)
