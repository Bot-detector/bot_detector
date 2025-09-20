from fastapi import APIRouter

from .health import health
from .models import models

router = APIRouter()
router.include_router(health.router, tags=["health"])
router.include_router(models.router, tags=["models"])
