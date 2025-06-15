from fastapi import APIRouter

from . import highscore

router = APIRouter()
router.include_router(highscore.router)
