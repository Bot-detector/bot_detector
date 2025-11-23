import logging

import pytest
from bot_detector.structs._metadata import MetaData
from bot_detector.structs.kafka.reports_to_insert import ReportsToInsertStruct
from bot_detector.structs.reports import Equipment, ParsedDetection

from bases.bot_detector.worker_report.main import parse_detections

logger = logging.getLogger(__name__)


@pytest.mark.asyncio
async def test_parse_detections_valid_report():
    # Arrange
    valid_report_v1 = ReportsToInsertStruct(
        metadata=MetaData(version=1, source="test_source"),
        report=ParsedDetection(
            region_id=1,
            x_coord=2,
            y_coord=3,
            z_coord=4,
            ts=1234567890,
            manual_detect=0,
            on_members_world=1,
            on_pvp_world=0,
            world_number=301,
            equipment=Equipment(
                equip_head_id=0,
                equip_amulet_id=0,
                equip_torso_id=0,
                equip_legs_id=0,
                equip_boots_id=0,
                equip_cape_id=0,
                equip_hands_id=0,
                equip_weapon_id=0,
                equip_shield_id=0,
            ),
            equip_ge_value=1000,
            reporter_id=42,
            reported_id=84,
        ),
    )

    # Act
    parsed_detections = await parse_detections([valid_report_v1])

    # Assert
    assert len(parsed_detections) == 1
    assert parsed_detections[0] == valid_report_v1.report


@pytest.mark.asyncio
async def test_parse_detections_invalid_and_unsupported_reports():
    unsupported_version_report = ReportsToInsertStruct(
        metadata=MetaData(version=2, source="test_source"),
        report=ParsedDetection(
            region_id=1,
            x_coord=2,
            y_coord=3,
            z_coord=4,
            ts=1234567890,
            manual_detect=0,
            on_members_world=1,
            on_pvp_world=0,
            world_number=301,
            equipment=Equipment(
                equip_head_id=0,
                equip_amulet_id=0,
                equip_torso_id=0,
                equip_legs_id=0,
                equip_boots_id=0,
                equip_cape_id=0,
                equip_hands_id=0,
                equip_weapon_id=0,
                equip_shield_id=0,
            ),
            equip_ge_value=1000,
            reporter_id=42,
            reported_id=84,
        ),
    )

    reports = [unsupported_version_report]

    parsed_detections = await parse_detections(reports)

    assert len(parsed_detections) == 0


@pytest.mark.asyncio
async def test_parse_detections_valid_null_report():
    mock_report = ReportsToInsertStruct(
        metadata=MetaData(version=1, source="api_public"),
        report=ParsedDetection(
            region_id=12598,
            x_coord=3167,
            y_coord=3490,
            z_coord=0,
            ts=1763909384,
            manual_detect=0,
            on_members_world=1,
            on_pvp_world=0,
            world_number=490,
            equipment=Equipment(
                equip_head_id=None,
                equip_amulet_id=None,
                equip_torso_id=None,
                equip_legs_id=None,
                equip_boots_id=None,
                equip_cape_id=None,
                equip_hands_id=None,
                equip_weapon_id=None,
                equip_shield_id=None,
            ),
            equip_ge_value=0,
            reporter_id=398265,
            reported_id=233134407,
        ),
    )

    # Act
    parsed_detections = await parse_detections([mock_report])

    # Assert
    assert len(parsed_detections) == 1
    parsed_report = parsed_detections[0]
    assert parsed_report.equipment.equip_head_id is None
    assert parsed_report.equipment.equip_amulet_id is None
    logger.info(f"Parsed detections: {parsed_detections}")
