import logging

from bot_detector.api_public.src.core.fastapi.dependencies import auth
from bot_detector.database.api.structs import ApiUserTableStruct
from fastapi import APIRouter, Depends

router = APIRouter(tags=["User"])
logger = logging.getLogger(__name__)


@router.get("/users/me", tags=["Private"])
def read_current_user(user: ApiUserTableStruct = Depends(auth.get_current_user)):
    return {"username": user.username, "password": user.token}
