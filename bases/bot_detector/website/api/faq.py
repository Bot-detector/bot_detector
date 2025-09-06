from bot_detector.website.core.config import templates
from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/about")
async def faq(request: Request):
    return templates.TemplateResponse("pages/faq.html", {"request": request})
