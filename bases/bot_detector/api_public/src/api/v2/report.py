import logging

from bot_detector.api_public.src.app.views.response.ok import Ok
from bot_detector.api_public.src.core.fastapi.dependencies.kafka import kafka_manager
from bot_detector.api_public.src.core.fastapi.dependencies.session import get_session
from bot_detector.player_services import PlayerService, SimpleALRUCache
from bot_detector.reporting import ReportProcessingError, ReportService
from bot_detector.structs import Detection
from fastapi import APIRouter, Depends, status
from fastapi.exceptions import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Report"])

player_cache = SimpleALRUCache(max_size=100_000)
report_service = ReportService(source="api_public")


@router.post("/report", status_code=status.HTTP_201_CREATED, response_model=Ok)
async def post_reports(
    detections: list[Detection],
    session: AsyncSession = Depends(get_session),
):
    player_service = PlayerService(session=session, cache=player_cache)

    data, error = report_service.validate(detections)
    if error or not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=error)

    logger.debug("Received: %s, Reporter: %s", len(data), data[0].reporter)

    try:
        parsed = await report_service.build_parsed_detections(
            detections=data, player_service=player_service
        )
        producer = kafka_manager.get_producer(key="reports_to_insert")
        await report_service.send_to_kafka(parsed=parsed, producer=producer)
    except ReportProcessingError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )
    return Ok()
