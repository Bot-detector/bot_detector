from bot_detector.api_public.src.app.repositories.player import Player
from bot_detector.api_public.src.app.repositories.report import Report
from bot_detector.api_public.src.app.views.response.ok import Ok
from bot_detector.api_public.src.core._cache import SimpleALRUCache
from bot_detector.api_public.src.core.fastapi.dependencies.queue import (
    get_reports_to_insert_producer,
)
from bot_detector.api_public.src.core.fastapi.dependencies import wide_event
from bot_detector.api_public.src.core.fastapi.dependencies.session import get_session
from bot_detector.event_queue.core import QueueProducer
from bot_detector.event_queue.structs import ReportsToInsertStruct
from bot_detector.structs import Detection, ParsedDetection
from fastapi import APIRouter, Depends, status
from fastapi.exceptions import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["Report"])

player_cache = SimpleALRUCache(max_size=100_000)


@router.post("/report", status_code=status.HTTP_201_CREATED, response_model=Ok)
async def post_reports(
    detections: list[Detection],
    session: AsyncSession = Depends(get_session),
    report_producer: QueueProducer[ReportsToInsertStruct] = Depends(
        get_reports_to_insert_producer
    ),
):
    global player_cache
    report_repo = Report()
    player_repo = Player(session=session, cache=player_cache)

    wide_event.add_context(
        {
            "report": {
                "reports_received": len(detections),
                "sample_report": detections[0].model_dump() if detections else None,
            }
        }
    )
    data, error = await report_repo.parse_data(detections)
    if error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=error)

    wide_event.add_context(
        {
            "report": {
                "valid_reports_received": len(data),
                "reporter": data[0].reporter,
            }
        }
    )

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
            wide_event.add_context(
                {
                    "report": {
                        "status": "error",
                        "detail": "invalid_reporter_or_reported, could not find player id",
                        "reported": reported,
                        "reporter": reporter,
                    }
                }
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="something went wrong",
            )
        _d["reported_id"] = reported_id
        _d["reporter_id"] = reporter_id

        _data.append(ParsedDetection(**_d))

    # print(_data)
    produce_errors = await report_repo.send_to_queue(
        data=_data,
        producer=report_producer,
    )
    if produce_errors:
        wide_event.add_context(
            {
                "report": {
                    "status": "error",
                    "detail": str(produce_errors[0]),
                    "produce_errors": len(produce_errors),
                }
            }
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )
    return Ok()
