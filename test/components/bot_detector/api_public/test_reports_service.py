import time

import pytest

from components.bot_detector.api_public.services import ReportsService
from components.bot_detector.api_public.structs.reports import Detection, Equipment


def _make_detection(ts: int | None = None, reporter: str = "tester", reported: str = "target") -> Detection:
    equipment = Equipment(
        equip_head_id=1,
        equip_amulet_id=1,
        equip_torso_id=1,
        equip_legs_id=1,
        equip_boots_id=1,
        equip_cape_id=1,
        equip_hands_id=1,
        equip_weapon_id=1,
        equip_shield_id=1,
    )
    return Detection(
        reporter=reporter,
        reported=reported,
        region_id=1,
        x_coord=1,
        y_coord=1,
        z_coord=0,
        ts=ts if ts is not None else int(time.time()),
        manual_detect=0,
        on_members_world=0,
        on_pvp_world=0,
        world_number=301,
        equipment=equipment,
        equip_ge_value=1,
    )


@pytest.mark.asyncio()
async def test_parse_data_rejects_large_payload():
    service = ReportsService()
    detections = [_make_detection(reported=f"target-{i}") for i in range(5001)]

    data, error = await service.parse_data(detections)

    assert data is None
    assert error == "invalid data size"


@pytest.mark.asyncio()
async def test_parse_data_detects_invalid_unique_reporter():
    service = ReportsService()
    detections = [
        _make_detection(reporter="alpha", reported="x"),
        _make_detection(reporter="beta", reported="y"),
    ]

    data, error = await service.parse_data(detections)

    assert data is None
    assert error == "invalid unique reporter"
