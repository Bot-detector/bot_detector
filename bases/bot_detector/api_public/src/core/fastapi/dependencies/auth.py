import logging
from typing import Annotated

from bot_detector.api_public.src.core.fastapi.dependencies.session import get_session
from bot_detector.database.api import ApiUserRepo
from bot_detector.database.api.structs import ApiUserTableStruct
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["User"])
logger = logging.getLogger(__name__)

security = HTTPBasic()


async def get_current_user(
    credentials: Annotated[HTTPBasicCredentials, Depends(security)],
    session: AsyncSession = Depends(get_session),
) -> ApiUserTableStruct | None:
    _api_user_repo = ApiUserRepo()
    async with session.begin():
        user = await _api_user_repo.get_user(
            async_session=session,
            user_name=credentials.username,
            is_active=True,
        )
        if user and user.token == credentials.password:
            return user
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
    )


def has_permission(permission: str):
    async def _dependency(
        user: ApiUserTableStruct = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> ApiUserTableStruct:

        _api_user_repo = ApiUserRepo()

        async with session.begin():
            has_perm = await _api_user_repo.has_permission(
                async_session=session,
                permission=permission,
                token=user.token,
                user_name=user.username,
            )

        if not has_perm:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )

        return user

    return _dependency
