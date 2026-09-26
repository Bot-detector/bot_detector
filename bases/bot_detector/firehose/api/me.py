import logging
from typing import Annotated

from bot_detector.firehose.api.dependencies import ApiKey
from bot_detector.firehose.app.auth.auth import ANONYMOUS_USER
from bot_detector.firehose.app.state import FirehoseState
from fastapi import APIRouter, Query, Request

router = APIRouter(tags=["Me"])
logger = logging.getLogger(__name__)


@router.get("/me", summary="Validate credential; return identity and scopes")
async def me(
    request: Request,
    api_key: ApiKey,
    topic: Annotated[str, Query()] = "players.scraped",
) -> dict[str, str | None | bool | list[str]]:
    """Validate the token, then the allowlist, then report scopes.

    - no credential  -> anonymous, allowed (shared consumer group)
    - bad credential -> allowed=false (invalid token or not allowlisted)
    - ok             -> identity + every permission the user holds
    """
    state: FirehoseState = request.app.state.firehose
    user = await state.auth_repo.authenticate(api_key=api_key, topic=topic)
    if not api_key:
        return {
            "user": ANONYMOUS_USER,
            "token": None,
            "allowed": True,
            "scopes": [],
        }
    if isinstance(user, Exception):
        logger.info(f"credential rejected: {user}")
        return {
            "user": ANONYMOUS_USER,
            "token": None,
            "allowed": False,
            "scopes": [],
        }
    return {
        "user": user.name,
        "token": api_key,
        "allowed": True,
        "scopes": user.scopes,
    }
