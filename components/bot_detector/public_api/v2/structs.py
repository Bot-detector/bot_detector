from datetime import datetime
from typing import Any

from pydantic import BaseModel


class Equipment(BaseModel):
    equip_head_id: int | None = None
    equip_amulet_id: int | None = None
    equip_torso_id: int | None = None
    equip_legs_id: int | None = None
    equip_boots_id: int | None = None
    equip_cape_id: int | None = None
    equip_hands_id: int | None = None
    equip_weapon_id: int | None = None
    equip_shield_id: int | None = None


class Detection(BaseModel):
    equipment: Equipment
    reporter: str
    reported: str
    region_id: int = 0
    x_coord: int = 0
    y_coord: int = 0
    z_coord: int = 0
    ts: int = 0
    manual_detect: int = 0
    on_members_world: int = 0
    on_pvp_world: int = 0
    world_number: int = 0
    equip_ge_value: int = 0


class FeedbackInput(BaseModel):
    player_name: str
    vote: int
    prediction: str
    subject_id: int
    confidence: float | None = 0
    feedback_text: str | None = None
    proposed_label: str | None = None


class PredictionResponse(BaseModel):
    player_id: int
    player_name: str
    prediction_label: str
    prediction_confidence: float
    created: datetime
    predictions_breakdown: dict[str, Any]


class ReportScoreResponse(BaseModel):
    count: int
    possible_ban: bool
    confirmed_ban: bool
    confirmed_player: bool
    manual_detect: bool


class FeedbackScoreResponse(BaseModel):
    count: int
    possible_ban: bool
    confirmed_ban: bool
    confirmed_player: bool


class LabelResponse(BaseModel):
    id: int
    label: str


class Ok(BaseModel):
    detail: str = "ok"
