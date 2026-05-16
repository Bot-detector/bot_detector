import asyncio
from typing import Annotated

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
from bot_detector.database.api_public import PlayerRepo
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic.fields import Field

router = APIRouter(tags=["Player"])


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
    repo = PlayerRepo(session)
    names = await asyncio.gather(*[to_jagex_name(n) for n in name])
    data = await repo.get_report_score(player_names=tuple(names))
    return data


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
    repo = PlayerRepo(session)
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
    repo = PlayerRepo(session)
    names = await asyncio.gather(*[to_jagex_name(n) for n in name])
    data = await repo.get_prediction(player_names=names)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Player not found",
        )
    return [PredictionResponse.from_data(d, breakdown) for d in data]
