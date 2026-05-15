import random
import time
from typing import Generator

from pydantic import BaseModel, Field
from seeders.players_to_scrape import PlayerStruct


class Equipment(BaseModel):
    equip_head_id: int | None = Field(None, ge=0)
    equip_amulet_id: int | None = Field(None, ge=0)
    equip_torso_id: int | None = Field(None, ge=0)
    equip_legs_id: int | None = Field(None, ge=0)
    equip_boots_id: int | None = Field(None, ge=0)
    equip_cape_id: int | None = Field(None, ge=0)
    equip_hands_id: int | None = Field(None, ge=0)
    equip_weapon_id: int | None = Field(None, ge=0)
    equip_shield_id: int | None = Field(None, ge=0)


class ParsedDetection(BaseModel):
    reporter_id: int = Field(..., ge=0)
    reported_id: int = Field(..., ge=0)
    region_id: int = Field(0, ge=0, le=100_000)
    x_coord: int = Field(0, ge=0)
    y_coord: int = Field(0, ge=0)
    z_coord: int = Field(0, ge=0)
    ts: int = Field(default_factory=lambda: int(time.time()), ge=0)
    manual_detect: int = Field(0, ge=0, le=1)
    on_members_world: int = Field(0, ge=0, le=1)
    on_pvp_world: int = Field(0, ge=0, le=1)
    world_number: int = Field(0, ge=300, le=1_000)
    equipment: Equipment
    equip_ge_value: int = Field(0, ge=0)


class MetaData(BaseModel):
    version: int
    source: str


class ReportToInsertStruct(BaseModel):
    metadata: MetaData
    report: ParsedDetection


def create_reports_to_insert(
    players: list[PlayerStruct], reports_per_player: int
) -> Generator[ReportToInsertStruct, None, None]:
    for player in players:
        for _ in range(reports_per_player):
            reporter = random.choice(players)
            yield ReportToInsertStruct(
                metadata=MetaData(version=1, source="init"),
                report=ParsedDetection(
                    reporter_id=reporter.id,
                    reported_id=player.id,
                    region_id=random.randint(0, 100_000),
                    x_coord=random.randint(0, 5000),
                    y_coord=random.randint(0, 5000),
                    z_coord=random.randint(0, 3),
                    ts=int(time.time()),
                    manual_detect=0,
                    on_members_world=random.choice([0, 1]),
                    on_pvp_world=random.choice([0, 1]),
                    world_number=random.randint(300, 1_000),
                    equipment=Equipment(
                        equip_head_id=random.randint(0, 500),
                        equip_torso_id=random.randint(0, 500),
                        equip_legs_id=random.randint(0, 500),
                        equip_boots_id=random.randint(0, 500),
                        equip_weapon_id=random.randint(0, 500),
                        equip_amulet_id=random.randint(0, 500),
                        equip_cape_id=random.randint(0, 500),
                        equip_hands_id=random.randint(0, 500),
                        equip_shield_id=random.randint(0, 500),
                    ),
                    equip_ge_value=random.randint(0, 1_000_000),
                ),
            )
