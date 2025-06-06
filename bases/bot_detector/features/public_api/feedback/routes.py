import logging

from bot_detector.api_public.src.core.fastapi.dependencies.session import get_session
from bot_detector.api_public.src.core.fastapi.dependencies.to_jagex_name import (
    to_jagex_name,
)
from bot_detector.features.public_api.feedback.schemas import FeedbackInput
from bot_detector.features.public_api.feedback.service import Feedback
from bot_detector.features.public_api.response.schemas import Ok
from fastapi import APIRouter, Depends, HTTPException, status

router = APIRouter(tags=["Feedback"])
logger = logging.getLogger(__name__)


@router.post("/feedback", response_model=Ok, status_code=status.HTTP_201_CREATED)
async def post_feedback(
    feedback: FeedbackInput,
    session=Depends(get_session),
):
    """ """
    _feedback = Feedback(session)

    feedback.player_name = await to_jagex_name(feedback.player_name)

    success, detail = await _feedback.insert_feedback(feedback=feedback)
    if not success:
        raise HTTPException(status_code=422, detail=detail)
    return Ok()
