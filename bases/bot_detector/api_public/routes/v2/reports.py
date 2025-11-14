import logging

from components.bot_detector.api_public.services import PlayerService, ReportsService
from components.bot_detector.api_public.services.reports import CustomError
from components.bot_detector.api_public.structs.reports import (
    Detection,
    ParsedDetection,
)
from components.bot_detector.api_public.structs.responses import Ok
from bot_detector.cache.simple import SimpleALRUCache
from bases.bot_detector.api_public.core.fastapi.dependencies.session import get_session
from fastapi import APIRouter, Depends, status
from fastapi.exceptions import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["Report"])
logger = logging.getLogger(__name__)
player_cache = SimpleALRUCache(max_size=100_000)


@router.post("/report", status_code=status.HTTP_201_CREATED, response_model=Ok)
async def post_reports(
    detections: list[Detection],
    session: AsyncSession = Depends(get_session),
):
    global player_cache
    report_repo = ReportsService()
    player_repo = PlayerService(session=session, cache=player_cache)

    data, error = await report_repo.parse_data(detections)
    if error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=error)

    logger.debug(f"Received: {len(data)}, Reporter: {data[0].reporter}")

    player_names = list(set([d.reported for d in data] + [d.reporter for d in data]))
    players = [await player_repo.get_or_insert(player_name=p) for p in player_names]
    players = {p.name: p.id for p in players if p}

    _data = []
    for d in data:
        payload = d.model_dump()
        reported = player_repo.sanitize_name(payload.pop("reported"))
        reported_id = players.get(reported)
        reporter = player_repo.sanitize_name(payload.pop("reporter"))
        reporter_id = players.get(reporter)
        if reporter_id is None or reported_id is None:
            logger.warning(msg=f"{reported_id=}, {reporter_id=}, {d}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="something went wrong",
            )
        payload["reported_id"] = reported_id
        payload["reporter_id"] = reporter_id
        _data.append(ParsedDetection(**payload))

    try:
        await report_repo.send_to_kafka(data=_data)
    except CustomError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )
    return Ok()
