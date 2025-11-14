from fastapi import APIRouter

from bases.bot_detector.api_public.routes.v2.player import router as player_router
from bases.bot_detector.api_public.routes.v2.reports import router as reports_router
from bases.bot_detector.api_public.routes.v2.feedback import router as feedback_router
from bases.bot_detector.api_public.routes.v2.labels import router as labels_router


def _build_v2() -> APIRouter:
    api_router = APIRouter(prefix="/v2")
    for feature_router in (
        player_router,
        reports_router,
        feedback_router,
        labels_router,
    ):
        api_router.include_router(feature_router)
    return api_router


router = APIRouter()
router.include_router(_build_v2())

__all__ = ["router"]
