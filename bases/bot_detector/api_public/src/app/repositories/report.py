import asyncio
import logging
import time

from bot_detector.api_public.src.core.fastapi.dependencies import wide_event
from bot_detector.event_queue.core import QueueProducer
from bot_detector.event_queue.structs import ReportsToInsertStruct
from bot_detector.structs import (
    Detection,
    MetaData,
    ParsedDetection,
)
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

        stale_report_count = 0
        future_report_count = 0
        for d in data:
            if d.ts <= min_ts:
                stale_report_count += 1
                continue
            if d.ts >= max_ts:
                future_report_count += 1
                continue
            output.append(d)
        wide_event.add_context(
            {
                "report": {
                    "stale_report_count": stale_report_count,
                    "future_report_count": future_report_count,
                }
            }
        )
        return output

    def _check_unique_reporter(self, data: list[Detection]) -> list[Detection] | None:
        reporters = set(d.reporter for d in data)
        wide_event.add_context({"report": {"reporters": list(reporters)}})
        return None if len(reporters) > 1 else data

    async def parse_data(self, data: list[Detection]) -> tuple[list[Detection], None]:
        """
        Parse and validate a list of detection data.
        """
        data = self._check_data_size(data)
        if not data:
            error = "invalid data size"
            wide_event.add_context({"report": {"status": "error", "detail": error}})
            return None, error

        data = self._filter_valid_time(data)
        if not data:
            error = "invalid time"
            wide_event.add_context({"report": {"status": "error", "detail": error}})
            return None, error

        data = self._check_unique_reporter(data)
        if not data:
            error = "invalid unique reporter"
            wide_event.add_context({"report": {"status": "error", "detail": error}})
            return None, error
        return data, None

    def _transform_detection(
        self, data: list[ParsedDetection]
    ) -> tuple[list[ReportsToInsertStruct], list[str]]:
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

    async def send_to_kafka(
        self,
        data: list[ParsedDetection],
        producer: QueueProducer[ReportsToInsertStruct],
    ) -> None:
        tasks = []

        # Transform data to ReportsToInsertStruct
        reports, error = self._transform_detection(data)

        tasks = [producer.put([report]) for report in reports]
        produce_results = await asyncio.gather(*tasks)
        produce_errors = [
            result for result in produce_results if isinstance(result, Exception)
        ]
        if produce_errors:
            raise CustomError(f"Failed to send reports to kafka: {produce_errors[0]}")

        if len(error) > 0:
            error_msg = f"Received {len(error)} validation errors like this: {error[0]}"
            wide_event.add_context(
                {
                    "report": {
                        "reports_sent_to_kafka": len(reports),
                        "report_errors": len(error),
                    }
                }
            )
            raise CustomError(error_msg)
