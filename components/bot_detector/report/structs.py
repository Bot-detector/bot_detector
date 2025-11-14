import time
from typing import Optional

from pydantic import BaseModel, Field


class Metadata(BaseModel):
    version: str


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


class BaseDetection(BaseModel):
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


class Detection(BaseDetection):
    reporter: str = Field(..., min_length=1, max_length=13)
    reported: str = Field(..., min_length=1, max_length=12)


class ParsedDetection(BaseDetection):
    reporter_id: int = Field(..., ge=0)
    reported_id: int = Field(..., ge=0)


class KafkaDetectionV1(BaseDetection):
    metadata: Metadata = Metadata(version="v1.0.0")
    reporter: str = Field(..., min_length=1, max_length=13)
    reported: str = Field(..., min_length=1, max_length=12)


class KafkaDetectionV2(BaseDetection):
    metadata: Metadata = Metadata(version="v2.0.0")
    reporter_id: int = Field(..., ge=0)
    reported_id: int = Field(..., ge=0)


__all__ = [
    "Metadata",
    "Equipment",
    "BaseDetection",
    "Detection",
    "ParsedDetection",
    "KafkaDetectionV1",
    "KafkaDetectionV2",
]
