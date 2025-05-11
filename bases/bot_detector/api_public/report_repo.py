import asyncio
import logging
import time

from src.app.views.input.report import (
    Detection,
    KafkaDetectionV1,
    KafkaDetectionV2,
    ParsedDetection,
)
from src.core.fastapi.dependencies import kafka_engine

logger = logging.getLogger(__name__)


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

    async def parse_data(self, data: list[Detection]) -> list[Detection] | None:
        """
        Parse and validate a list of detection data.
        """
        data = self._check_data_size(data)
        if not data:
            logger.warning("invalid data size")
            return None

        data = self._filter_valid_time(data)
        if not data:
            logger.warning("invalid time")
            return None

        data = self._check_unique_reporter(data)
        if not data:
            logger.warning("invalid unique reporter")
            return None
        return data

    def detection_to_v1(self, data: list[Detection]) -> list[KafkaDetectionV1]:
        return [KafkaDetectionV1(**d.model_dump()) for d in data]

    def detection_to_v2(self, data: list[ParsedDetection]) -> list[KafkaDetectionV2]:
        return [KafkaDetectionV2(**d.model_dump()) for d in data]

    async def send_to_kafka(
        self, data: list[Detection] | list[ParsedDetection]
    ) -> None:
        detections = []
        v1, v2 = [], []
        for d in data:
            if isinstance(d, Detection):
                v1.append(d)
            elif isinstance(d, ParsedDetection):
                v2.append(d)
        v1 = self.detection_to_v1(data=v1)
        v2 = self.detection_to_v2(data=v2)

        detections: list[dict] = [d.model_dump(mode="json") for d in v1 + v2]
        send_queue = kafka_engine.producer.get_queue()
        await asyncio.gather(*[send_queue.put(d) for d in detections])
        return
