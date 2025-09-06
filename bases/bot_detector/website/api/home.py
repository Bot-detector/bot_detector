from bot_detector.website.core.config import BD_API, templates
from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()


class Stats(BaseModel):
    total_bans: int
    total_real_players: int
    total_accounts: int


@router.get("/home")
async def home(request: Request):
    stats = await BD_API.get_project_stats()
    stats = Stats(**stats)
    response = {"request": request, "stats": stats.dict()}
    return templates.TemplateResponse("pages/home.html", response)
