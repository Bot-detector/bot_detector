from fastapi import APIRouter

from bases.bot_detector.api_public import feedback, labels, player, reports

router = APIRouter()
v2_router = APIRouter(prefix="/v2")

for feature_router in (
    player.router,
    reports.router,
    feedback.router,
    labels.router,
):
    v2_router.include_router(feature_router)

router.include_router(v2_router)

__all__ = ["router"]
