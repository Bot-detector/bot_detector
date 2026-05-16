from bot_detector.api_public.src.app.views.response.label import LabelResponse
from bot_detector.api_public.src.core.fastapi.dependencies import wide_event
from bot_detector.api_public.src.core.fastapi.dependencies.session import get_session
from bot_detector.database.api_public import LabelRepo
from fastapi import APIRouter, Depends, status

router = APIRouter(tags=["Labels"])


@router.get(
    "/labels",
    response_model=list[LabelResponse],
    status_code=status.HTTP_200_OK,
)
async def get_labels(session=Depends(get_session)):
    _fn = get_labels.__name__
    wide_event.add_context({_fn: {}})
    _label_repo = LabelRepo(session)
    labels = await _label_repo.get_labels()

    _labels = []
    for label in labels:
        _label = LabelResponse(**label.__dict__)
        _label.label = _label.label.lower()
        _labels.append(_label)
    wide_event.add_context({_fn: {"status": "success", "labels_count": len(_labels)}})
    return _labels


@router.get(
    "/labels/{label_id}",
    response_model=LabelResponse | None,
    status_code=status.HTTP_200_OK,
)
async def get_label_by_id(
    label_id: int, session=Depends(get_session)
) -> LabelResponse | None:
    _fn = get_label_by_id.__name__
    wide_event.add_context({_fn: {"label_id": label_id}})
    _label_repo = LabelRepo(session)
    label = await _label_repo.get_label_by_id(label_id=label_id)

    if label is None:
        wide_event.add_context({_fn: {"status": "not_found", "label_id": label_id}})
        return None
    _label = LabelResponse(**label.__dict__)
    _label.label = _label.label.lower()
    wide_event.add_context({_fn: {"status": "success", "label_id": label_id}})
    return _label
