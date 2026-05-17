from bot_detector.api_public.src.core.fastapi.dependencies import auth, wide_event
from bot_detector.database.api.structs import ApiUserTableStruct
from fastapi import APIRouter, Depends

router = APIRouter(tags=["User"])


@router.get("/users/me", tags=["Private"])
def read_current_user(user: ApiUserTableStruct = Depends(auth.get_current_user)):
    _fn = read_current_user.__name__
    wide_event.add_context({_fn: {"status": "called"}})
    return {"username": user.username, "password": user.token}
