import logging

from bot_detector.api_public.src.app.repositories.report import CustomError, Report
from bot_detector.api_public.src.app.views.input.report import Detection
from bot_detector.api_public.src.app.views.response.ok import Ok
from fastapi import APIRouter, status
from fastapi.exceptions import HTTPException

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Report"])


@router.post("/report", status_code=status.HTTP_201_CREATED, response_model=Ok)
async def post_reports(detections: list[Detection]):
    report = Report()
    data, error = await report.parse_data(detections)
    if error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=error)
    logger.debug(f"Working: {len(data)}")

    try:
        await report.send_to_kafka(data=data)
    except CustomError:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal error"
        )

    return Ok()
