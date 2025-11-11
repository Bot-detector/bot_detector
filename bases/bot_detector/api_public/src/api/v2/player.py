import asyncio
import logging
from typing import Annotated

from bot_detector.api_public.src.core.fastapi.dependencies.session import get_session
from bot_detector.api_public.src.core.fastapi.dependencies.to_jagex_name import (
    to_jagex_name,
)
from bot_detector.player_services import PlayerService
from bot_detector.structs import (
    FeedbackScoreResponse,
    PredictionResponse,
    ReportScoreResponse,
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
        description="Name of the player",
        examples=["Player1", "Player2"],
    ),
    session=Depends(get_session),
):
    repo = PlayerService(session)
    names = await asyncio.gather(*[to_jagex_name(n) for n in name])
    return await repo.get_report_score(player_names=tuple(names))


@router.get("/player/feedback/score", response_model=list[FeedbackScoreResponse])
async def get_feedback_score(
    name: list[Annotated[str, Field(..., min_length=1, max_length=13)]] = Query(
        ...,
        min_length=1,
        description="Name of the player",
        examples=["Player1", "Player2"],
    ),
    session=Depends(get_session),
):
    repo = PlayerService(session)
    names = await asyncio.gather(*[to_jagex_name(n) for n in name])
    return await repo.get_feedback_score(player_names=names)


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
    repo = PlayerService(session)
    names = await asyncio.gather(*[to_jagex_name(n) for n in name])
    predictions = await repo.enrich_predictions(player_names=names, breakdown=breakdown)
    if not predictions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Player not found"
        )
    return predictions
