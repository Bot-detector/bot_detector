from fastapi import APIRouter

from components.bot_detector.feedback import feedback

from . import player, report

router = APIRouter()
router.include_router(player.router)
router.include_router(report.router)
router.include_router(feedback.router)
