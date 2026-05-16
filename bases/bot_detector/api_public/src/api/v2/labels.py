import logging

from bot_detector.api_public.src.app.views.response.label import LabelResponse
from bot_detector.api_public.src.core.fastapi.dependencies.session import get_session
from bot_detector.database.api_public import LabelRepo
from fastapi import APIRouter, Depends, status

router = APIRouter(tags=["Labels"])
logger = logging.getLogger(__name__)


@router.get(
    "/labels",
    response_model=list[LabelResponse],
    status_code=status.HTTP_200_OK,
)
async def get_labels(session=Depends(get_session)):
    _label_repo = LabelRepo(session)
    labels = await _label_repo.get_labels()

    _labels = []
    for label in labels:
        _label = LabelResponse(**label.__dict__)
        _label.label = _label.label.lower()
        _labels.append(_label)
    return _labels


@router.get(
    "/labels/{label_id}",
    response_model=LabelResponse | None,
    status_code=status.HTTP_200_OK,
)
async def get_label_by_id(
    label_id: int, session=Depends(get_session)
) -> LabelResponse | None:
    _label_repo = LabelRepo(session)
    label = await _label_repo.get_label_by_id(label_id=label_id)

    if label is None:
        return None
    _label = LabelResponse(**label.__dict__)
    _label.label = _label.label.lower()
    return _label
