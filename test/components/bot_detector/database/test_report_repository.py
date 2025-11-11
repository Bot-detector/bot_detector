from datetime import datetime

from bot_detector.database.repositories import ReportRepo
from bot_detector.structs import Equipment, ParsedDetection


def _sample_detection(ts: int | None = None, equip_weapon_id: int = 18) -> ParsedDetection:
    equipment = Equipment(
        equip_head_id=10,
        equip_amulet_id=11,
        equip_torso_id=12,
        equip_legs_id=13,
        equip_boots_id=14,
        equip_cape_id=15,
        equip_hands_id=16,
        equip_weapon_id=equip_weapon_id,
        equip_shield_id=19,
    )
    return ParsedDetection(
        region_id=1,
        x_coord=3200,
        y_coord=3200,
        z_coord=0,
        ts=ts or 1_700_000_000,
        manual_detect=1,
        on_members_world=1,
        on_pvp_world=0,
        world_number=301,
        equipment=equipment,
        equip_ge_value=123,
        reporter_id=42,
        reported_id=84,
    )


def test_parse_reports_converts_epoch_to_datetime():
    repo = ReportRepo()
    parsed = repo._parse_reports([_sample_detection()])

    assert len(parsed) == 1
    converted = parsed[0]
    assert isinstance(converted["timestamp"], datetime)
    assert converted["reporter_id"] == 42
    assert converted["reported_id"] == 84


def test_parse_reports_clamps_large_equipment_values():
    repo = ReportRepo()
    parsed = repo._parse_reports([_sample_detection(equip_weapon_id=40000)])

    assert parsed[0]["equip_weapon_id"] == 0


def test_parse_reports_ignores_invalid_items():
    repo = ReportRepo()
    parsed = repo._parse_reports([_sample_detection(), "not-a-detection"])  # type: ignore[arg-type]

    assert len(parsed) == 1
