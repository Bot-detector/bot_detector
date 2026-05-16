import os
import time

import pytest

os.environ.setdefault("DATABASE_URL", "mysql+asyncmy://test:test@localhost/test")
os.environ.setdefault("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

from bot_detector.api_public.src.app.report import ReportService
from bot_detector.structs import Detection, Equipment


def _make_detection(**overrides) -> Detection:
    defaults = dict(
        reporter="testreporter",
        reported="testreported",
        region_id=0,
        x_coord=0,
        y_coord=0,
        z_coord=0,
        ts=int(time.time()),
        manual_detect=0,
        on_members_world=0,
        on_pvp_world=0,
        world_number=500,
        equipment=Equipment(),
        equip_ge_value=0,
    )
    defaults.update(overrides)
    return Detection(**defaults)


class TestReportService:
    @pytest.mark.asyncio
    async def test_parse_data_returns_data_on_valid_input(self):
        service = ReportService()
        detections = [
            _make_detection(),
            _make_detection(reporter="testreporter", reported="bot1"),
        ]
        data, error = await service.parse_data(detections)
        assert data is not None
        assert error is None
        assert len(data) == 2

    @pytest.mark.asyncio
    async def test_parse_data_rejects_too_many_reports(self):
        service = ReportService()
        detections = [_make_detection() for _ in range(5001)]
        data, error = await service.parse_data(detections)
        assert data is None
        assert error == "invalid data size"

    @pytest.mark.asyncio
    async def test_parse_data_rejects_stale_timestamps(self):
        service = ReportService()
        detections = [_make_detection(ts=int(time.time()) - 30000)]
        data, error = await service.parse_data(detections)
        assert data is None
        assert error == "invalid time"

    @pytest.mark.asyncio
    async def test_parse_data_rejects_future_timestamps(self):
        service = ReportService()
        detections = [_make_detection(ts=int(time.time()) + 5000)]
        data, error = await service.parse_data(detections)
        assert data is None
        assert error == "invalid time"

    @pytest.mark.asyncio
    async def test_parse_data_rejects_multiple_reporters(self):
        service = ReportService()
        detections = [
            _make_detection(reporter="reporter_a"),
            _make_detection(reporter="reporter_b"),
        ]
        data, error = await service.parse_data(detections)
        assert data is None
        assert error == "invalid unique reporter"
