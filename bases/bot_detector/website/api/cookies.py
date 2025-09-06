from bot_detector.website.core.config import templates
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/cookies")
async def cookies(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("pages/cookies.html", {"request": request})
