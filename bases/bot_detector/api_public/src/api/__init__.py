from fastapi import APIRouter

from . import v2

print("API v2 loaded")
router = APIRouter()
router.include_router(v2.router, prefix="/v2")
