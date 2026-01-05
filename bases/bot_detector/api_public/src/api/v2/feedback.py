import logging

from bot_detector.api_public.src.app.repositories.feedback import Feedback
from bot_detector.api_public.src.app.views.input.feedback import FeedbackInput
from bot_detector.api_public.src.app.views.response.ok import Ok
from bot_detector.api_public.src.core.fastapi.dependencies import wide_event
from bot_detector.api_public.src.core.fastapi.dependencies.session import get_session
from bot_detector.api_public.src.core.fastapi.dependencies.to_jagex_name import (
    to_jagex_name,
)
from fastapi import APIRouter, Depends, HTTPException, status

router = APIRouter(tags=["Feedback"])
logger = logging.getLogger(__name__)


@router.post("/feedback", response_model=Ok, status_code=status.HTTP_201_CREATED)
async def post_feedback(
    feedback: FeedbackInput,
    session=Depends(get_session),
):
    _feedback = Feedback(session)

    feedback.player_name = await to_jagex_name(feedback.player_name)

    # Add request-level wide_event context for feedback

    wide_event.add_context({"feedback": feedback.model_dump()})

    success, detail = await _feedback.insert_feedback(feedback=feedback)
    if not success:
        raise HTTPException(status_code=422, detail=detail)
    return Ok(detail=detail)
