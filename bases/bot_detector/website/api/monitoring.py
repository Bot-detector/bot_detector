from bot_detector.website.app.schemas.extras.health import Health
from bot_detector.website.core import Settings
from fastapi import APIRouter

router = APIRouter()


@router.get("/monitoring", response_model=Health)
async def health() -> Health:
    return Health(version=Settings().RELEASE_VERSION, status="Healthy")
