from urllib.parse import urlencode

from bot_detector.website.core.config import BD_API, templates
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, Response

router = APIRouter()


@router.get("/account-search")
async def get_account_search(request: Request, name: str = "") -> Response:
    stripped = name.strip()
    if name != stripped:
        url = "/account-search"
        if stripped:
            url = f"{url}?{urlencode({'name': stripped})}"
        return RedirectResponse(url=url, status_code=303)
    predictions: list = []
    if stripped:
        predictions = await BD_API.get_prediction(name=stripped)
    response = {"request": request, "predictions": predictions, "name": stripped}
    return templates.TemplateResponse("pages/account_search.html", response)
