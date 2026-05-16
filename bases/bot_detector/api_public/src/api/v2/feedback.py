import logging
from typing import Annotated

from bot_detector.api_public.src.app.views.input.feedback import FeedbackInput
from bot_detector.api_public.src.app.views.response.ok import Ok
from bot_detector.api_public.src.core.fastapi.dependencies import wide_event
from bot_detector.api_public.src.core.fastapi.dependencies.auth import (
    AuthenticatedUser,
    require_permission,
)
from bot_detector.api_public.src.core.fastapi.dependencies.session import get_session
from bot_detector.api_public.src.core.fastapi.dependencies.to_jagex_name import (
    to_jagex_name,
)
from bot_detector.database.api_public import FeedbackRepo, PlayerRepo
from bot_detector.database.feedback import FeedbackExportRepo
from bot_detector.structs import FeedbackExportResponse
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic.fields import Field

router = APIRouter(tags=["Feedback"])
logger = logging.getLogger(__name__)

_feedback_export_repo = FeedbackExportRepo()


@router.post("/feedback", response_model=Ok, status_code=status.HTTP_201_CREATED)
async def post_feedback(
    feedback: FeedbackInput,
    session=Depends(get_session),
):
    _feedback = FeedbackRepo(session)

    feedback.player_name = await to_jagex_name(feedback.player_name)

    wide_event.add_context({"feedback": feedback.model_dump()})

    success, detail = await _feedback.insert_feedback(
        feedback_data=feedback.model_dump()
    )
    if not success:
        wide_event.add_context({"feedback": {"status": "error", "detail": detail}})
        raise HTTPException(status_code=422, detail=detail)
    wide_event.add_context({"feedback": {"status": "success"}})
    return Ok(detail=detail)


@router.get("/feedback/export", response_model=FeedbackExportResponse)
async def get_feedback_export(
    player_name: Annotated[str, Field(..., min_length=1, max_length=13)] = Query(
        ...,
        description="Normalized OSRS username of the voter",
    ),
    user: AuthenticatedUser = Depends(
        require_permission("discord_general", "feedback_export")
    ),
    session=Depends(get_session),
):
    player_name = await to_jagex_name(player_name)

    player_repo = PlayerRepo(session)
    player = await player_repo.get(player_name=player_name)

    if player is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Player not found",
        )

    feedback_items = await _feedback_export_repo.get_feedback_export(
        async_session=session,
        voter_player_id=player.id,
    )

    if not feedback_items:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return FeedbackExportResponse(
        player_name=player_name,
        total_feedback=len(feedback_items),
        feedback=feedback_items,
    )
