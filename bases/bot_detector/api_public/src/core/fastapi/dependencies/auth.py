import base64
import logging

from bot_detector.database.api import ApiUserRepo
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from .session import get_session

logger = logging.getLogger(__name__)

_api_user_repo = ApiUserRepo()


class AuthenticatedUser:
    def __init__(self, user_id: int, username: str, token: str):
        self.user_id = user_id
        self.username = username
        self.token = token


async def verify_token(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> AuthenticatedUser:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing token",
        )

    bearer_token = auth_header[len("Bearer ") :]

    try:
        decoded = base64.b64decode(bearer_token).decode("utf-8")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing token",
        )

    if ":" not in decoded:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing token",
        )

    username, token = decoded.split(":", 1)

    user = await _api_user_repo.get_user(session, username, is_active=True)

    if user is None or user.token != token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing token",
        )

    return AuthenticatedUser(user_id=user.id, username=user.username, token=user.token)


def require_permission(permission: str, route: str):
    async def _check(
        user: AuthenticatedUser = Depends(verify_token),
        session: AsyncSession = Depends(get_session),
    ) -> AuthenticatedUser:
        has_perm = await _api_user_repo.has_permission(
            session, user.username, user.token, permission
        )
        if not has_perm:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )

        await _api_user_repo.log_usage(session, user.user_id, route)

        return user

    return _check
