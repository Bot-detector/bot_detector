import time
from typing import Optional

from pydantic import BaseModel
from pydantic.fields import Field


class Equipment(BaseModel):
    equip_head_id: Optional[int] = Field(None, ge=0)
    equip_amulet_id: Optional[int] = Field(None, ge=0)
    equip_torso_id: Optional[int] = Field(None, ge=0)
    equip_legs_id: Optional[int] = Field(None, ge=0)
    equip_boots_id: Optional[int] = Field(None, ge=0)
    equip_cape_id: Optional[int] = Field(None, ge=0)
    equip_hands_id: Optional[int] = Field(None, ge=0)
    equip_weapon_id: Optional[int] = Field(None, ge=0)
    equip_shield_id: Optional[int] = Field(None, ge=0)


class Detection(BaseModel):
    reporter: str = Field(..., min_length=1, max_length=13)
    reported: str = Field(..., min_length=1, max_length=12)
    region_id: int = Field(0, ge=0, le=100_000)
    x_coord: int = Field(0, ge=0)
    y_coord: int = Field(0, ge=0)
    z_coord: int = Field(0, ge=0)
    ts: int = Field(int(time.time()), ge=0)
    manual_detect: int = Field(0, ge=0, le=1)
    on_members_world: int = Field(0, ge=0, le=1)
    on_pvp_world: int = Field(0, ge=0, le=1)
    world_number: int = Field(0, ge=300, le=1_000)
    equipment: Equipment
    equip_ge_value: int = Field(0, ge=0)
