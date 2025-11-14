import datetime

from bot_detector.report.database.repository import ReportRepo
from bot_detector.report.structs import Equipment, ParsedDetection


def _parsed_detection() -> ParsedDetection:
    return ParsedDetection(
        reporter_id=1,
        reported_id=2,
        region_id=1,
        x_coord=10,
        y_coord=20,
        z_coord=0,
        ts=1,
        manual_detect=0,
        on_members_world=0,
        on_pvp_world=0,
        world_number=301,
        equip_ge_value=123,
        equipment=Equipment(
            equip_head_id=1,
            equip_amulet_id=2,
            equip_torso_id=3,
            equip_legs_id=4,
            equip_boots_id=5,
            equip_cape_id=6,
            equip_hands_id=7,
            equip_weapon_id=8,
            equip_shield_id=9,
        ),
    )


def test_parse_reports_flattens_and_converts():
    repo = ReportRepo()
    result = repo._parse_reports([_parsed_detection()])

    assert len(result) == 1
    flattened = result[0]
    assert flattened["reporter_id"] == 1
    assert flattened["equip_head_id"] == 1
    assert isinstance(flattened["timestamp"], datetime.datetime)


def test_parse_reports_skips_invalid_entries():
    repo = ReportRepo()

    result = repo._parse_reports(["not-a-detection"])

    assert result == []
