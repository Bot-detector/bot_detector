import asyncio
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


class CustomError(Exception): ...


class ReportService:
    def _check_data_size(self, data: list[Detection]) -> list[Detection] | None:
        return None if len(data) > 5000 else data

    def _filter_valid_time(self, data: list[Detection]) -> list[Detection]:
        _fn = self._filter_valid_time.__name__
        current_time = int(time.time())
        min_ts = current_time - 25200
        max_ts = current_time + 3600
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
                _fn: {
                    "stale_report_count": stale_report_count,
                    "future_report_count": future_report_count,
                }
            }
        )
        return output

    def _check_unique_reporter(self, data: list[Detection]) -> list[Detection] | None:
        _fn = self._check_unique_reporter.__name__
        reporters = set(d.reporter for d in data)
        wide_event.add_context({_fn: {"reporters": list(reporters)}})
        return None if len(reporters) > 1 else data

    async def parse_data(self, data: list[Detection]) -> tuple[list[Detection], None]:
        _fn = self.parse_data.__name__
        data = self._check_data_size(data)
        if not data:
            error = "invalid data size"
            wide_event.add_context({_fn: {"status": "error", "detail": error}})
            return None, error

        data = self._filter_valid_time(data)
        if not data:
            error = "invalid time"
            wide_event.add_context({_fn: {"status": "error", "detail": error}})
            return None, error

        data = self._check_unique_reporter(data)
        if not data:
            error = "invalid unique reporter"
            wide_event.add_context({_fn: {"status": "error", "detail": error}})
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

    async def send_to_queue(
        self,
        data: list[ParsedDetection],
        producer: QueueProducer[ReportsToInsertStruct],
    ) -> list[Exception]:
        _fn = self.send_to_queue.__name__
        reports, error = self._transform_detection(data)

        tasks = [producer.put([report]) for report in reports]
        produce_results = await asyncio.gather(*tasks, return_exceptions=True)
        produce_errors = [
            result for result in produce_results if isinstance(result, Exception)
        ]

        if len(error) > 0:
            wide_event.add_context(
                {
                    _fn: {
                        "reports_sent_to_queue": len(reports),
                        "report_errors": len(error),
                    }
                }
            )
            produce_errors.append(
                CustomError(
                    f"Received {len(error)} validation errors like this: {error[0]}"
                )
            )

        return produce_errors
