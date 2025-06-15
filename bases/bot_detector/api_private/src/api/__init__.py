from fastapi import APIRouter

from . import v2, v3, v4

router = APIRouter()
router.include_router(v2.router, prefix="/v2")
router.include_router(v3.router, prefix="/v3")
router.include_router(v4.router, prefix="/v4")
