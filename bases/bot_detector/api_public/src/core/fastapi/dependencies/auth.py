import base64
import logging

from bot_detector.database.api import ApiUserRepo
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from .session import get_session

logger = logging.getLogger(__name__)

_api_user_repo = ApiUserRepo()
_bearer_scheme = HTTPBearer()

NOT_AUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or missing token",
)


class AuthenticatedUser:
    def __init__(self, user_id: int, username: str, token: str):
        self.user_id = user_id
        self.username = username
        self.token = token


async def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> AuthenticatedUser:
    bearer_token = credentials.credentials

    try:
        decoded = base64.b64decode(bearer_token).decode("utf-8")
    except Exception:
        raise NOT_AUTHENTICATED

    if ":" not in decoded:
        raise NOT_AUTHENTICATED

    username, token = decoded.split(":", 1)

    user = await _api_user_repo.get_user(session, username, is_active=True)

    if user is None or user.token != token:
        raise NOT_AUTHENTICATED

    return AuthenticatedUser(user_id=user.id, username=user.username, token=user.token)


def require_permission(permission: str, route: str):
    async def _check(
        user: AuthenticatedUser = Depends(verify_token),
        session: AsyncSession = Depends(get_session),
    ) -> AuthenticatedUser:
        has_perm = await _api_user_repo.has_permission(
            session, permission, user.token, user_name=user.username
        )
        if not has_perm:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )

        await _api_user_repo.log_usage(session, user.user_id, route)

        return user

    return _check
