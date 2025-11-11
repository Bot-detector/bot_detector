import asyncio
import logging
from typing import Iterable, Optional

from bot_detector.kafka.repositories import RepoReportsToInsertProducer
from bot_detector.player_services import PlayerService
from bot_detector.structs import (
    Detection,
    MetaData,
    ParsedDetection,
    ReportsToInsertStruct,
)
from pydantic import ValidationError

from ..domain import validators

logger = logging.getLogger(__name__)


class ReportProcessingError(Exception):
    """Raised when report processing fails."""


class ReportService:
    """Business logic for validating and dispatching reports."""

    def __init__(self, *, source: str = "api_public"):
        self.source = source

    def validate(self, detections: list[Detection]) -> tuple[Optional[list[Detection]], Optional[str]]:
        data = validators.check_data_size(detections)
        if not data:
            return None, "invalid data size"

        data = validators.filter_valid_time(data)
        if not data:
            return None, "invalid time"

        data = validators.check_unique_reporter(data)
        if not data:
            return None, "invalid unique reporter"
        return data, None

    async def build_parsed_detections(
        self,
        detections: Iterable[Detection],
        player_service: PlayerService,
    ) -> list[ParsedDetection]:
        player_names = validators.collect_player_names(detections)
        players = await player_service.ensure_player_ids(player_names)

        parsed: list[ParsedDetection] = []
        for detection in detections:
            data = detection.model_dump()
            reported_name = player_service.sanitize_name(data.pop("reported"))
            reporter_name = player_service.sanitize_name(data.pop("reporter"))

            reported_id = players.get(reported_name)
            reporter_id = players.get(reporter_name)
            if reported_id is None or reporter_id is None:
                logger.warning(
                    "missing player ids reporter=%s(%s) reported=%s(%s)",
                    reporter_name,
                    reporter_id,
                    reported_name,
                    reported_id,
                )
                raise ReportProcessingError("Failed to resolve player ids")

            data["reported_id"] = reported_id
            data["reporter_id"] = reporter_id
            parsed.append(ParsedDetection(**data))
        return parsed

    def _transform_detection(
        self, parsed: Iterable[ParsedDetection]
    ) -> tuple[list[ReportsToInsertStruct], list[str]]:
        reports: list[ReportsToInsertStruct] = []
        errors: list[str] = []

        for detection in parsed:
            metadata = MetaData(version=1, source=self.source)
            try:
                reports.append(
                    ReportsToInsertStruct(
                        metadata=metadata,
                        report=detection.model_dump(),
                    )
                )
            except ValidationError as exc:
                errors.append(f"Validation error: {exc.json()}")
        return reports, errors

    async def send_to_kafka(
        self,
        parsed: list[ParsedDetection],
        producer: RepoReportsToInsertProducer,
    ) -> None:
        if producer is None:
            raise ReportProcessingError("Producer not configured")

        reports, errors = self._transform_detection(parsed)
        tasks = [producer.produce_one(report=report) for report in reports]
        if tasks:
            await asyncio.gather(*tasks)

        if errors:
            logger.error(
                "Received %s validation errors while sending reports, example=%s",
                len(errors),
                errors[0],
            )
            raise ReportProcessingError("Validation error while sending reports")
