import random
from datetime import datetime, timedelta
from typing import Generator

from pydantic import BaseModel


class ReportSighting(BaseModel):
    reporting_id: int
    reported_id: int
    manual_detect: int


class ReportGear(BaseModel):
    equip_head_id: int | None
    equip_amulet_id: int | None
    equip_torso_id: int | None
    equip_legs_id: int | None
    equip_boots_id: int | None
    equip_cape_id: int | None
    equip_hands_id: int | None
    equip_weapon_id: int | None
    equip_shield_id: int | None


class ReportLocation(BaseModel):
    region_id: int
    x_coord: int
    y_coord: int
    z_coord: int


class Report(BaseModel):
    report_sighting_id: int
    report_location_id: int
    report_gear_id: int
    reported_at: datetime
    on_members_world: int | None
    on_pvp_world: int | None
    world_number: int | None
    region_id: int


def create_report_sightings(
    player_ids: list[int], count: int
) -> Generator[ReportSighting, None, None]:
    for _ in range(count):
        reporting_id = random.choice(player_ids)
        reported_id = random.choice(player_ids)
        while reported_id == reporting_id:
            reported_id = random.choice(player_ids)

        yield ReportSighting(
            reporting_id=reporting_id,
            reported_id=reported_id,
            manual_detect=random.choice([0, 0, 0, 1]),
        )


def create_report_gear(count: int) -> Generator[ReportGear, None, None]:
    for _ in range(count):
        yield ReportGear(
            equip_head_id=random.randint(1, 25000) if random.random() > 0.1 else None,
            equip_amulet_id=random.randint(1, 25000) if random.random() > 0.1 else None,
            equip_torso_id=random.randint(1, 25000) if random.random() > 0.1 else None,
            equip_legs_id=random.randint(1, 25000) if random.random() > 0.1 else None,
            equip_boots_id=random.randint(1, 25000) if random.random() > 0.1 else None,
            equip_cape_id=random.randint(1, 25000) if random.random() > 0.1 else None,
            equip_hands_id=random.randint(1, 25000) if random.random() > 0.1 else None,
            equip_weapon_id=random.randint(1, 25000) if random.random() > 0.1 else None,
            equip_shield_id=random.randint(1, 25000) if random.random() > 0.3 else None,
        )


def create_report_locations(count: int) -> Generator[ReportLocation, None, None]:
    for _ in range(count):
        yield ReportLocation(
            region_id=random.randint(1, 15000),
            x_coord=random.randint(0, 10000),
            y_coord=random.randint(0, 10000),
            z_coord=random.randint(0, 3),
        )


def create_reports(
    sighting_ids: list[int],
    gear_ids: list[int],
    location_ids: list[int],
    count: int,
) -> Generator[Report, None, None]:
    base_time = datetime.now() - timedelta(days=30)

    for i in range(count):
        sighting_id = (
            sighting_ids[i] if i < len(sighting_ids) else random.choice(sighting_ids)
        )
        location_id = (
            location_ids[i] if i < len(location_ids) else random.choice(location_ids)
        )
        gear_id = gear_ids[i] if i < len(gear_ids) else random.choice(gear_ids)

        yield Report(
            report_sighting_id=sighting_id,
            report_location_id=location_id,
            report_gear_id=gear_id,
            reported_at=base_time + timedelta(minutes=random.randint(0, 43200)),
            on_members_world=random.choice([0, 1]),
            on_pvp_world=random.choice([0, 0, 0, 1]),
            world_number=random.randint(300, 500),
            region_id=random.randint(1, 15000),
        )
