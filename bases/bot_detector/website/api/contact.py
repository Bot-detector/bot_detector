from bot_detector.website.core.config import templates
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/contact")
async def contact(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("pages/contact.html", {"request": request})
