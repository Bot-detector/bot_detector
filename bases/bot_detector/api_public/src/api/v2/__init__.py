from bot_detector.features.public_api import feedback
from fastapi import APIRouter

from . import player, report

router = APIRouter()
router.include_router(player.router)
router.include_router(report.router)
router.include_router(feedback.router)
