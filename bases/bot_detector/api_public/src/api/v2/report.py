import logging

from bot_detector.api_public.src.app.repositories.player import Player
from bot_detector.api_public.src.app.repositories.report import CustomError, Report
from bot_detector.api_public.src.core._cache import SimpleALRUCache
from bot_detector.api_public.src.core.fastapi.dependencies.session import get_session
from bot_detector.features.public_api.response.schemas import Ok
from bot_detector.structs import Detection, ParsedDetection
from fastapi import APIRouter, Depends, status
from fastapi.exceptions import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Report"])

player_cache = SimpleALRUCache(max_size=100_000)


@router.post("/report", status_code=status.HTTP_201_CREATED, response_model=Ok)
async def post_reports(
    detections: list[Detection],
    session: AsyncSession = Depends(get_session),
):
    global player_cache
    report_repo = Report()
    player_repo = Player(session=session, cache=player_cache)

    data, error = await report_repo.parse_data(detections)
    if error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=error)

    logger.debug(f"Received: {len(data)}, Reporter: {data[0].reporter}")

    # get unique list of names
    player_names = list(set([d.reported for d in data] + [d.reporter for d in data]))
    players = [await player_repo.get_or_insert(player_name=p) for p in player_names]
    players = {p.name: p.id for p in players if p}

    _data = []
    for d in data:
        _d = d.model_dump()
        # get reported_id from name
        reported = player_repo.sanitize_name(_d.pop("reported"))
        reported_id = players.get(reported)

        # get reporter_id from name
        reporter = player_repo.sanitize_name(_d.pop("reporter"))
        reporter_id = players.get(reporter)

        # some validation
        if reporter_id is None or reported_id is None:
            logger.warning(msg=f"{reported_id=}, {reporter_id=}, {d}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="something went wrong",
            )
        _d["reported_id"] = reported_id
        _d["reporter_id"] = reporter_id

        _data.append(ParsedDetection(**_d))

    print(_data)
    try:
        await report_repo.send_to_kafka(data=_data)
    except CustomError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )
    return Ok()
