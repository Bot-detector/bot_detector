import logging

from bot_detector.labels.services import LabelService
from bot_detector.labels.structs import LabelResponse
from bases.bot_detector.api_public.core.fastapi.dependencies.session import get_session
from fastapi import APIRouter, Depends, status

router = APIRouter(tags=["Labels"])
logger = logging.getLogger(__name__)


@router.get("/labels", response_model=list[LabelResponse], status_code=status.HTTP_200_OK)
async def get_labels(session=Depends(get_session)):
    repo = LabelService(session)
    labels = await repo.get_labels()
    _labels = []
    for label in labels:
        res = LabelResponse(**label.__dict__)
        res.label = res.label.lower()
        _labels.append(res)
    return _labels


@router.get("/labels/{label_id}", response_model=LabelResponse | None)
async def get_label_by_id(label_id: int, session=Depends(get_session)) -> LabelResponse | None:
    repo = LabelService(session)
    label = await repo.get_label_by_id(label_id=label_id)
    if label is None:
        return None
    res = LabelResponse(**label.__dict__)
    res.label = res.label.lower()
    return res
