from fastapi import APIRouter

from . import feedback, labels, player, report, user

router = APIRouter()
router.include_router(player.router)
router.include_router(report.router)
router.include_router(feedback.router)
router.include_router(labels.router)
router.include_router(user.router)
