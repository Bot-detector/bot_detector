import asyncio
import logging
from typing import Annotated

from bot_detector.api_public.src.app.repositories.player import Player as repoPlayer
from bot_detector.api_public.src.app.views.response.feedback_score import (
    FeedbackScoreResponse,
)
from bot_detector.api_public.src.app.views.response.prediction import PredictionResponse
from bot_detector.api_public.src.app.views.response.report_score import (
    ReportScoreResponse,
)
from bot_detector.api_public.src.core.fastapi.dependencies.session import get_session
from bot_detector.api_public.src.core.fastapi.dependencies.to_jagex_name import (
    to_jagex_name,
)
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic.fields import Field

router = APIRouter(tags=["Player"])
logger = logging.getLogger(__name__)


@router.get("/player/report/score", response_model=list[ReportScoreResponse])
async def get_players_kc(
    name: list[Annotated[str, Field(..., min_length=1, max_length=13)]] = Query(
        ...,
        min_length=1,
        max_length=5,
        description="Name of the player",
        examples=["Player1", "Player2"],
    ),
    session=Depends(get_session),
):
    """
    Get the report score for one or multiple players.

    Args:
        name (str): can be provided multiple times

    Returns:
        list[ReportScoreResponse]: A list of dictionaries containing KC data for each player.
    """
    repo = repoPlayer(session)
    names = await asyncio.gather(*[to_jagex_name(n) for n in name])
    data = await repo.get_report_score(player_names=names)
    return data


@router.get("/player/feedback/score", response_model=list[FeedbackScoreResponse])
async def get_feedback_score(
    name: list[Annotated[str, Field(..., min_length=1, max_length=13)]] = Query(
        ...,
        min_length=1,
        max_length=5,
        description="Name of the player",
        examples=["Player1", "Player2"],
    ),
    session=Depends(get_session),
):
    """
    Get the feedback score for one or multiple players.

    Args:
        name (str): can be provided multiple times

    Returns:
        list[FeedbackScoreResponse]: A list of dictionaries containing KC data for each player.
    """
    repo = repoPlayer(session)
    names = await asyncio.gather(*[to_jagex_name(n) for n in name])
    data = await repo.get_feedback_score(player_names=names)
    return data


@router.get("/player/prediction", response_model=list[PredictionResponse])
async def get_prediction(
    name: list[Annotated[str, Field(..., min_length=1, max_length=13)]] = Query(
        ...,
        min_length=1,
        max_length=5,
        description="Name of the player",
        examples=["Player1", "Player2"],
    ),
    breakdown: bool = Query(...),
    session=Depends(get_session),
):
    """
    Get prediction data for one or multiple users.

    Args:
        name (str): The username of the user for whom predictions are requested.
        breakdown (bool): A flag indicating whether to include a breakdown of predictions.

    Returns:
        List[PredictionResponse]: A list of PredictionResponse objects containing prediction data.

    Raises:
        HTTPException: Returns a 404 error with the message "Player not found" if no data is found for the user.

    """
    repo = repoPlayer(session)
    names = await asyncio.gather(*[to_jagex_name(n) for n in name])
    data = await repo.get_prediction(player_names=names)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Player not found"
        )
    return [PredictionResponse.from_data(d, breakdown) for d in data]
