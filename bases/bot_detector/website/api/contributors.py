from bot_detector.website.core.config import templates
from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/contributors")
async def contributors(request: Request):
    return templates.TemplateResponse("pages/contributors.html", {"request": request})
