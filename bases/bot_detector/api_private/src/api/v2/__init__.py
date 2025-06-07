from fastapi import APIRouter
from . import player, highscore

router = APIRouter()
router.include_router(player.router)
router.include_router(highscore.router)
