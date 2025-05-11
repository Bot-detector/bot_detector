from fastapi import APIRouter

from . import feedback, player, report

router = APIRouter()
router.include_router(player.router)
router.include_router(report.router)
router.include_router(feedback.router)
